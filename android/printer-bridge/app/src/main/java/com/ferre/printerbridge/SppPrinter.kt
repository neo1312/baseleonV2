package com.ferre.printerbridge

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothSocket
import java.io.OutputStream
import java.util.UUID

/**
 * Bluetooth Classic SPP transport for ESC/POS thermal printers.
 * The printer must be paired once in Android Settings (PIN 1234).
 */
class SppPrinter(private val mac: String) {

    companion object {
        val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
    }

    private var socket: BluetoothSocket? = null
    private var out: OutputStream? = null

    @SuppressLint("MissingPermission")
    fun connect() {
        if (socket?.isConnected == true) return
        val adapter = BluetoothAdapter.getDefaultAdapter()
            ?: throw IllegalStateException("No hay adaptador Bluetooth")
        if (!adapter.isEnabled) throw IllegalStateException("Bluetooth apagado")
        val device = adapter.getRemoteDevice(mac)
        adapter.cancelDiscovery()
        val s = device.createRfcommSocketToServiceRecord(SPP_UUID)
        s.connect()
        socket = s
        out = s.outputStream
    }

    fun isConnected(): Boolean = socket?.isConnected == true

    /** Write bytes in chunks with a small delay to avoid overflowing the printer buffer. */
    fun write(data: ByteArray, chunkSize: Int = 256, delayMs: Long = 25) {
        val o = out ?: throw IllegalStateException("Impresora no conectada")
        var i = 0
        while (i < data.size) {
            val end = minOf(i + chunkSize, data.size)
            o.write(data, i, end - i)
            o.flush()
            i = end
            if (i < data.size) Thread.sleep(delayMs)
        }
    }

    fun close() {
        try { out?.close() } catch (_: Exception) {}
        try { socket?.close() } catch (_: Exception) {}
        out = null
        socket = null
    }
}
