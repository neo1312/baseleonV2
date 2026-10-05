package com.ferre.printerbridge

import android.content.Context

/** Simple SharedPreferences wrapper for the bridge configuration. */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("printer_bridge", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = sp.getString("base_url", "") ?: ""
        set(v) = sp.edit().putString("base_url", v.trim()).apply()

    var token: String
        get() = sp.getString("token", "") ?: ""
        set(v) = sp.edit().putString("token", v.trim()).apply()

    var printerMac: String
        get() = sp.getString("printer_mac", "") ?: ""
        set(v) = sp.edit().putString("printer_mac", v.trim()).apply()

    var printerName: String
        get() = sp.getString("printer_name", "") ?: ""
        set(v) = sp.edit().putString("printer_name", v.trim()).apply()

    var intervalSec: Int
        get() = sp.getInt("interval", 3)
        set(v) = sp.edit().putInt("interval", v).apply()

    var autoStart: Boolean
        get() = sp.getBoolean("auto_start", true)
        set(v) = sp.edit().putBoolean("auto_start", v).apply()
}
