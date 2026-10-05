package com.ferre.printerbridge

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast

class MainActivity : Activity() {

    private lateinit var prefs: Prefs
    private lateinit var urlInput: EditText
    private lateinit var tokenInput: EditText
    private lateinit var intervalInput: EditText
    private lateinit var autoStartCheck: CheckBox
    private lateinit var deviceSpinner: Spinner
    private lateinit var statusText: TextView

    private val pairedDevices = mutableListOf<BluetoothDevice>()
    private var pendingPermissions = false

    private val handler = Handler(Looper.getMainLooper())
    private val statusTick = object : Runnable {
        override fun run() {
            refreshStatus()
            handler.postDelayed(this, 1000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        setContentView(buildUi())
        requestRuntimePermissions()
        loadPairedDevices()
        refreshStatus()

        // Auto-start the bridge if it was already configured.
        if (prefs.baseUrl.isNotBlank() && prefs.printerMac.isNotBlank() && !PrintService.running) {
            PrintService.start(this)
        }
    }

    override fun onResume() {
        super.onResume()
        handler.post(statusTick)
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacks(statusTick)
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private fun buildUi(): ViewGroup {
        val root = ScrollView(this)
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(20), dp(20), dp(20))
        }
        root.addView(col)

        col.addView(label("Servidor (URL base)", top = 0))
        urlInput = EditText(this).apply {
            hint = "5.75.162.179  o  http://5.75.162.179:8087"
            setText(prefs.baseUrl)
            inputType = android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        col.addView(urlInput)

        col.addView(label("Token (X-Print-Token)"))
        tokenInput = EditText(this).apply { setText(prefs.token) }
        col.addView(tokenInput)

        col.addView(label("Impresora emparejada (SPP)"))
        deviceSpinner = Spinner(this)
        col.addView(deviceSpinner)

        col.addView(label("Intervalo de consulta (segundos)"))
        intervalInput = EditText(this).apply {
            inputType = android.text.InputType.TYPE_CLASS_NUMBER
            setText(prefs.intervalSec.toString())
        }
        col.addView(intervalInput)

        autoStartCheck = CheckBox(this).apply {
            text = "Iniciar al encender la tablet"
            isChecked = prefs.autoStart
        }
        col.addView(autoStartCheck)

        val saveBtn = Button(this).apply {
            text = "Guardar"
            setOnClickListener { saveConfig() }
        }
        col.addView(saveBtn)

        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val startBtn = Button(this).apply {
            text = "Iniciar"
            setOnClickListener {
                saveConfig()
                PrintService.start(this@MainActivity)
                refreshStatus()
            }
        }
        val stopBtn = Button(this).apply {
            text = "Detener"
            setOnClickListener {
                PrintService.stop(this@MainActivity)
                refreshStatus()
            }
        }
        row.addView(startBtn, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(stopBtn, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        col.addView(row)

        val row2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val testBtn = Button(this).apply {
            text = "Probar impresión"
            setOnClickListener { testPrint() }
        }
        val pingBtn = Button(this).apply {
            text = "Probar conexión"
            setOnClickListener { testConnection() }
        }
        row2.addView(testBtn, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row2.addView(pingBtn, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        col.addView(row2)

        statusText = TextView(this).apply {
            setPadding(0, dp(16), 0, 0)
            textSize = 14f
        }
        col.addView(statusText)

        return root
    }

    private fun label(text: String, top: Int = 12): TextView = TextView(this).apply {
        this.text = text
        setPadding(0, dp(top), 0, dp(4))
    }

    private fun requestRuntimePermissions() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return
        val wanted = mutableListOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_SCAN)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            wanted.add(Manifest.permission.POST_NOTIFICATIONS)
        }
        val missing = wanted.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isNotEmpty()) {
            pendingPermissions = true
            requestPermissions(missing.toTypedArray(), 100)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 100) {
            pendingPermissions = false
            loadPairedDevices()
        }
    }

    @SuppressLint("MissingPermission")
    private fun loadPairedDevices() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
            checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED
        ) {
            return
        }
        pairedDevices.clear()
        val adapter = BluetoothAdapter.getDefaultAdapter()
        val devices = adapter?.bondedDevices?.toList() ?: emptyList()
        pairedDevices.addAll(devices)

        val names = pairedDevices.map { "${it.name ?: "?"}\n${it.address}" }
        val arr = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item, names)
        deviceSpinner.adapter = arr

        val saved = prefs.printerMac
        val idx = pairedDevices.indexOfFirst { it.address == saved }
        if (idx >= 0) deviceSpinner.setSelection(idx)

        if (pairedDevices.isEmpty()) {
            Toast.makeText(this, "Empareja la impresora en Ajustes Bluetooth (PIN 1234)", Toast.LENGTH_LONG).show()
        }
    }

    private fun saveConfig() {
        prefs.baseUrl = urlInput.text.toString()
        prefs.token = tokenInput.text.toString()
        prefs.intervalSec = intervalInput.text.toString().toIntOrNull() ?: 3
        prefs.autoStart = autoStartCheck.isChecked
        val pos = deviceSpinner.selectedItemPosition
        if (pos in pairedDevices.indices) {
            prefs.printerMac = pairedDevices[pos].address
            prefs.printerName = pairedDevices[pos].name ?: ""
        }
        Toast.makeText(this, "Guardado", Toast.LENGTH_SHORT).show()
        refreshStatus()
    }

    private fun testConnection() {
        saveConfig()
        val baseUrl = prefs.baseUrl
        if (baseUrl.isBlank()) {
            Toast.makeText(this, "Escribe la URL del servidor", Toast.LENGTH_LONG).show()
            return
        }
        Toast.makeText(this, "Probando conexión...", Toast.LENGTH_SHORT).show()
        Thread {
            try {
                val api = Api(this, baseUrl, prefs.token)
                val body = api.ping()
                runOnUiThread { Toast.makeText(this, "Conexión OK: $body", Toast.LENGTH_LONG).show() }
            } catch (e: Exception) {
                runOnUiThread { Toast.makeText(this, "Falló: ${e.message}", Toast.LENGTH_LONG).show() }
            }
        }.start()
    }

    private fun testPrint() {
        saveConfig()
        val mac = prefs.printerMac
        if (mac.isBlank()) {
            Toast.makeText(this, "Selecciona una impresora", Toast.LENGTH_LONG).show()
            return
        }
        Thread {
            val printer = SppPrinter(mac)
            try {
                printer.connect()
                val text = "\n   PRUEBA DE IMPRESION   \n\nImpresa correctamente\n\n\n"
                val bytes = byteArrayOf(0x1B, 0x40, 0x1B, 0x61, 0x01) +
                    text.toByteArray(Charsets.US_ASCII) + byteArrayOf(0x0A, 0x0A, 0x0A)
                printer.write(bytes)
                runOnUiThread { Toast.makeText(this, "Prueba enviada", Toast.LENGTH_SHORT).show() }
            } catch (e: Exception) {
                runOnUiThread { Toast.makeText(this, "Error: ${e.message}", Toast.LENGTH_LONG).show() }
            } finally {
                printer.close()
            }
        }.start()
    }

    private fun refreshStatus() {
        val running = PrintService.running
        statusText.text = buildString {
            append("Servicio: ")
            append(if (running) "ACTIVO" else "DETENIDO")
            append("\nEstado: ")
            append(PrintService.lastStatus)
            append("\nImpresora: ")
            append(prefs.printerName.ifBlank { prefs.printerMac.ifBlank { "(sin seleccionar)" } })
            append("\nServidor: ")
            append(prefs.baseUrl.ifBlank { "(sin configurar)" })
            if (pendingPermissions) append("\n\nSolicitando permisos de Bluetooth...")
        }
    }
}
