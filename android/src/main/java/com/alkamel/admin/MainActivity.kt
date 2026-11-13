package com.alkamel.admin

import android.app.Activity
import android.os.Bundle
import android.graphics.Typeface
import android.view.Gravity
import android.view.View
import android.widget.*
import org.json.JSONObject
import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val io = Executors.newSingleThreadExecutor()
    private val prefs by lazy { getSharedPreferences("admin", MODE_PRIVATE) }
    private lateinit var root: LinearLayout
    private lateinit var status: TextView
    private var token = ""
    private var base = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        token = prefs.getString("token", "") ?: ""
        base = prefs.getString("base", "http://192.168.1.2:8080") ?: "http://192.168.1.2:8080"
        renderHome()
    }
    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()
    private fun text(value: String, size: Float = 16f, bold: Boolean = false): TextView =
        TextView(this).apply { text = value; textSize = size; gravity = Gravity.RIGHT; setTextColor(0xff172033.toInt()); if (bold) setTypeface(null, Typeface.BOLD); setPadding(dp(8), dp(8), dp(8), dp(8)) }
    private fun button(label: String, action: () -> Unit) = Button(this).apply { text = label; setOnClickListener { action() } }
    private fun input(hint: String, value: String = "") = EditText(this).apply { this.hint = hint; setText(value); textSize = 15f; gravity = Gravity.RIGHT; setSingleLine(true) }
    private fun shell(title: String) {
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(12), dp(16), dp(12)); layoutDirection = View.LAYOUT_DIRECTION_RTL; setBackgroundColor(0xfff3f6fb.toInt()) }
        root.addView(text(title, 22f, true))
        status = text("إدارة محلية – شبكة الكامل", 12f); root.addView(status)
        val scroll = ScrollView(this); scroll.addView(root); setContentView(scroll)
    }
    private fun card(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(10), dp(12), dp(10)); setBackgroundColor(0xffffffff.toInt())
        val p = LinearLayout.LayoutParams(-1, -2); p.setMargins(0, dp(8), 0, dp(8)); root.addView(this, p)
    }
    private fun renderHome() {
        shell("إدارة شبكة الكامل")
        val c = card(); c.addView(text("عنوان الخادم المحلي"))
        val server = input("http://عنوان-الخادم:8080", base); c.addView(server)
        c.addView(button("حفظ عنوان الخادم") { base = server.text.toString().trim().trimEnd('/'); prefs.edit().putString("base", base).apply(); status.text = "تم حفظ العنوان" })
        if (token.isBlank()) {
            val pass = input("كلمة مرور المدير"); c.addView(pass)
            c.addView(button("تسجيل الدخول") {
                base = server.text.toString().trim().trimEnd('/')
                request("POST", "/api/login", JSONObject().put("password", pass.text.toString()), false) { result ->
                    token = result.optString("token")
                    if (token.isNotBlank()) { prefs.edit().putString("token", token).putString("base", base).apply(); runOnUiThread { renderDashboard() } }
                    else runOnUiThread { status.text = "تعذر تسجيل الدخول" }
                }
            })
        } else {
            c.addView(button("فتح لوحة الإدارة") { renderDashboard() })
            c.addView(button("تسجيل الخروج") { token = ""; prefs.edit().remove("token").apply(); renderHome() })
        }
    }
    private fun renderDashboard() {
        shell("لوحة التحكم"); val c = card()
        c.addView(button("تحديث الإحصائيات") { loadStats(c) })
        c.addView(button("إدارة الأقسام") { renderSections() })
        c.addView(button("إرسال رسالة للمشتركين") { renderSendMessage() })
        c.addView(button("تسجيل الخروج") { token = ""; prefs.edit().remove("token").apply(); renderHome() })
        loadStats(c)
    }
    private fun loadStats(container: LinearLayout) {
        request("GET", "/api/stats", null, true) { d -> runOnUiThread {
            container.addView(text("الأقسام: " + d.optInt("sections") + " | الظاهرة: " + d.optInt("visible_sections")))
            container.addView(text("الرسائل: " + d.optInt("messages") + " | الأجهزة النشطة: " + d.optInt("online_devices")))
        } }
    }
    private fun renderSections() {
        shell("إدارة الأقسام"); val c = card()
        val title = input("اسم القسم"); val desc = input("وصف القسم"); val icon = input("الأيقونة", "grid"); val target = input("معرّف الشاشة داخل تطبيق المشتركين")
        c.addView(title); c.addView(desc); c.addView(icon); c.addView(target)
        c.addView(button("إضافة القسم") {
            val body = JSONObject().put("title", title.text.toString()).put("description", desc.text.toString()).put("icon", icon.text.toString()).put("target", target.text.toString()).put("visible", true)
            request("POST", "/api/sections", body, true) { runOnUiThread { Toast.makeText(this, "تمت إضافة القسم", Toast.LENGTH_SHORT).show(); renderSections() } }
        })
        c.addView(button("تحديث القائمة") { loadSections(c) }); c.addView(button("رجوع") { renderDashboard() }); loadSections(c)
    }
    private fun loadSections(container: LinearLayout) {
        request("GET", "/api/sections", null, true) { d ->
            val arr = d.optJSONArray("sections") ?: JSONArray()
            runOnUiThread {
                for (i in 0 until arr.length()) {
                    val item = arr.optJSONObject(i) ?: continue
                    val row = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
                    row.addView(text(item.optString("title"), 17f, true))
                    row.addView(text(if (item.optInt("visible") == 1) "ظاهر" else "مخفي", 12f))
                    row.addView(button(if (item.optInt("visible") == 1) "إخفاء القسم" else "إظهار القسم") {
                        val patch = JSONObject().put("visible", item.optInt("visible") != 1)
                        request("PATCH", "/api/sections/" + item.optInt("id"), patch, true) { runOnUiThread { renderSections() } }
                    })
                    container.addView(row)
                }
            }
        }
    }
    private fun renderSendMessage() {
        shell("إرسال رسالة"); val c = card()
        val title = input("عنوان الرسالة")
        val body = EditText(this).apply { hint = "نص الرسالة"; minLines = 4; gravity = Gravity.TOP or Gravity.RIGHT }
        c.addView(title); c.addView(body)
        c.addView(button("إرسال لجميع الأجهزة") {
            val payload = JSONObject().put("title", title.text.toString()).put("body", body.text.toString()).put("audience", "all")
            request("POST", "/api/messages", payload, true) { runOnUiThread { Toast.makeText(this, "حُفظت الرسالة في الخادم", Toast.LENGTH_LONG).show(); renderDashboard() } }
        })
        c.addView(button("رجوع") { renderDashboard() })
    }
    private fun request(method: String, path: String, data: JSONObject?, authenticated: Boolean, done: (JSONObject) -> Unit) {
        io.execute {
            try {
                val conn = URL(base + path).openConnection() as HttpURLConnection
                conn.requestMethod = method; conn.connectTimeout = 5000; conn.readTimeout = 7000
                conn.setRequestProperty("Accept", "application/json")
                if (authenticated && token.isNotBlank()) conn.setRequestProperty("Authorization", "Bearer " + token)
                if (data != null) { conn.doOutput = true; conn.setRequestProperty("Content-Type", "application/json; charset=utf-8"); conn.outputStream.use { it.write(data.toString().toByteArray(Charsets.UTF_8)) } }
                val code = conn.responseCode
                val stream = if (code in 200..299) conn.inputStream else conn.errorStream
                val response = stream?.bufferedReader()?.use { it.readText() } ?: "{}"
                val result = JSONObject(response); conn.disconnect()
                if (code !in 200..299) throw Exception(result.optString("error", "فشل الطلب"))
                done(result)
            } catch (e: Exception) { runOnUiThread { status.text = e.message ?: "تعذر الاتصال بالخادم" } }
        }
    }
    override fun onDestroy() { super.onDestroy(); io.shutdown() }
}
