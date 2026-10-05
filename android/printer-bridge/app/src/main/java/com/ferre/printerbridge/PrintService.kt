package com.ferre.printerbridge

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Base64
import android.util.Log
import kotlin.concurrent.thread

/**
 * Foreground service that polls the remote print queue and prints jobs over SPP.
 * Runs even when the POS page/app is closed.
 */
class PrintService : Service() {

    companion object {
        private const val TAG = "PrintService"
        private const val CHANNEL_ID = "print_bridge"
        private const val NOTIF_ID = 1001

        @Volatile
        var running = false
            private set

        fun start(context: Context) {
            val i = Intent(context, PrintService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) context.startForegroundService(i)
            else context.startService(i)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, PrintService::class.java))
        }
    }

    private lateinit var prefs: Prefs

    @Volatile
    private var alive = true

    @Volatile
    private var lastStatus: String = "Iniciando..."

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        createChannel()
        startForeground(NOTIF_ID, buildNotification("Iniciando..."))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!running) {
            running = true
            thread(name = "print-loop") { loop() }
        }
        return START_STICKY
    }

    private fun loop() {
        while (alive) {
            val baseUrl = prefs.baseUrl
            val mac = prefs.printerMac
            if (baseUrl.isBlank() || mac.isBlank()) {
                lastStatus = "Configura URL e impresora"
                updateNotification()
                sleep(5000)
                continue
            }

            try {
                val api = Api(this, baseUrl, prefs.token)
                val jobs = api.pendingJobs()
                if (jobs.length() > 0) {
                    val printer = SppPrinter(mac)
                    try {
                        printer.connect()
                        for (i in 0 until jobs.length()) {
                            val job = jobs.getJSONObject(i)
                            val id = job.getInt("job_id")
                            val bytes = Base64.decode(job.getString("data_b64"), Base64.DEFAULT)
                            try {
                                printer.write(bytes)
                                api.ack(id)
                                lastStatus = "Impreso job #$id"
                                Log.i(TAG, "Printed job $id")
                            } catch (e: Exception) {
                                api.fail(id, e.message ?: "print error", true)
                                lastStatus = "Fallo job #$id"
                                Log.e(TAG, "Failed job $id", e)
                            }
                        }
                    } finally {
                        printer.close()
                    }
                } else {
                    lastStatus = "Esperando trabajos..."
                }
            } catch (e: Exception) {
                lastStatus = "Sin conexion: ${e.message}"
                Log.w(TAG, "Poll error: ${e.message}")
            }

            updateNotification()
            sleep((prefs.intervalSec.coerceIn(1, 60) * 1000).toLong())
        }
    }

    private fun sleep(ms: Long) {
        try {
            Thread.sleep(ms)
        } catch (_: InterruptedException) {
        }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ch = NotificationChannel(CHANNEL_ID, "Puente de impresion", NotificationManager.IMPORTANCE_LOW)
            ch.setShowBadge(false)
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(ch)
        }
    }

    private fun buildNotification(text: String): Notification {
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            Notification.Builder(this, CHANNEL_ID) else @Suppress("DEPRECATION") Notification.Builder(this)

        val pi = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        return builder
            .setContentTitle("Ferreteria - Impresora")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentIntent(pi)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification() {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(NOTIF_ID, buildNotification(lastStatus))
    }

    override fun onDestroy() {
        alive = false
        running = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
