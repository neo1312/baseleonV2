package com.ferre.printerbridge

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import java.security.cert.CertificateException
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import javax.net.ssl.HostnameVerifier
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager

/**
 * Minimal API client for the Django print queue.
 *
 * Trusts (a) the platform/system CAs and (b) the self-signed certificate bundled
 * in res/raw/ferre_cert.pem, so it works against https://<vps-ip> without a domain
 * and without installing anything on the tablet.
 */
class Api(context: Context, baseUrl: String, private val token: String) {

    private val appContext = context.applicationContext
    private val baseUrl = normalize(baseUrl)
    private val sslContext: SSLContext? by lazy { buildSslContext() }

    private fun normalize(raw: String): String {
        var u = raw.trim().trimEnd('/')
        if (u.isNotEmpty() && !u.startsWith("http://") && !u.startsWith("https://")) {
            u = "https://$u"
        }
        return u
    }

    private fun loadBundledCert(): X509Certificate? = try {
        val cf = CertificateFactory.getInstance("X.509")
        appContext.resources.openRawResource(R.raw.ferre_cert).use {
            cf.generateCertificate(it) as X509Certificate
        }
    } catch (e: Exception) {
        null
    }

    private fun buildSslContext(): SSLContext? {
        val cert = loadBundledCert() ?: return null

        val defaultTm = try {
            val tmf = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
            tmf.init(null as KeyStore?)
            tmf.trustManagers.filterIsInstance<X509TrustManager>().firstOrNull()
        } catch (e: Exception) {
            null
        }

        val customTm = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {}
            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                if (chain.isNullOrEmpty()) throw CertificateException("empty chain")
                if (chain[0] != cert) throw CertificateException("not the configured certificate")
                chain[0].checkValidity()
            }
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf(cert)
        }

        val combined = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                val c = chain ?: throw CertificateException("empty chain")
                defaultTm?.checkClientTrusted(c, authType)
            }

            override fun checkServerTrusted(chain: Array<out X509Certificate>?, authType: String?) {
                val c = chain ?: throw CertificateException("empty chain")
                try {
                    if (defaultTm != null) defaultTm.checkServerTrusted(c, authType)
                    else throw CertificateException("no default trust manager")
                } catch (e: Exception) {
                    customTm.checkServerTrusted(c, authType)
                }
            }

            override fun getAcceptedIssuers(): Array<X509Certificate> =
                (defaultTm?.acceptedIssuers ?: emptyArray()) + customTm.acceptedIssuers
        }

        return SSLContext.getInstance("TLS").apply {
            init(null, arrayOf<TrustManager>(combined), null)
        }
    }

    private fun open(path: String, method: String): HttpURLConnection {
        val conn = URL(baseUrl + path).openConnection() as HttpURLConnection
        if (conn is HttpsURLConnection) {
            sslContext?.let {
                conn.sslSocketFactory = it.socketFactory
                conn.hostnameVerifier = HostnameVerifier { _, _ -> true }
            }
        }
        conn.requestMethod = method
        conn.connectTimeout = 15000
        conn.readTimeout = 20000
        conn.setRequestProperty("X-Print-Token", token)
        conn.setRequestProperty("Accept", "application/json")
        return conn
    }

    fun pendingJobs(): JSONArray {
        val conn = open("/pos/print-jobs/pending/", "GET")
        return try {
            conn.inputStream.bufferedReader().use { JSONArray(it.readText()) }
        } finally {
            conn.disconnect()
        }
    }

    /** Connectivity/auth check. Returns the store name on success, throws otherwise. */
    fun ping(): String {
        val conn = open("/pos/print-jobs/ping/", "GET")
        return try {
            val code = conn.responseCode
            if (code in 200..299) {
                conn.inputStream?.bufferedReader()?.use { it.readText() } ?: ""
            } else {
                val err = conn.errorStream?.bufferedReader()?.use { it.readText() } ?: ""
                throw IllegalStateException("HTTP $code $err")
            }
        } finally {
            conn.disconnect()
        }
    }

    fun ack(jobId: Int) = post("/pos/print-jobs/$jobId/ack/", "{}")

    fun fail(jobId: Int, error: String, retry: Boolean) {
        val body = JSONObject().put("error", error.take(500)).put("retry", retry).toString()
        post("/pos/print-jobs/$jobId/fail/", body)
    }

    private fun post(path: String, body: String) {
        val conn = open(path, "POST")
        try {
            conn.doOutput = true
            conn.setRequestProperty("Content-Type", "application/json")
            conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            conn.inputStream.use { it.readBytes() }
        } finally {
            conn.disconnect()
        }
    }
}
