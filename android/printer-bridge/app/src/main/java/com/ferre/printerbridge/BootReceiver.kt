package com.ferre.printerbridge

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Starts the print bridge automatically after the tablet boots. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action == Intent.ACTION_BOOT_COMPLETED) {
            if (Prefs(context).autoStart) {
                PrintService.start(context)
            }
        }
    }
}
