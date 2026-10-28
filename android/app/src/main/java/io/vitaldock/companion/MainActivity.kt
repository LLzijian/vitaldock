package io.vitaldock.companion

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.PermissionController
import androidx.health.connect.client.permission.HealthPermission
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch
import java.security.SecureRandom

class MainActivity : ComponentActivity() {
    private lateinit var status: TextView
    private val request = registerForActivityResult(PermissionController.createRequestPermissionResultContract()) {
        refresh()
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = getSharedPreferences("pairing", MODE_PRIVATE)
        if (!prefs.contains("token")) prefs.edit().putString("token", ByteArray(32).also {
            SecureRandom().nextBytes(it)
        }.joinToString("") { "%02x".format(it) }).apply()
        val column = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(36, 48, 36, 36) }
        fun text(value: String) = TextView(this).apply { text = value; textSize = 17f; setPadding(0, 12, 0, 12); column.addView(this) }
        fun button(label: String, action: () -> Unit) { column.addView(Button(this).apply { text = label; setOnClickListener { action() } }) }
        text("VitalDock 健康连接").textSize = 25f
        text("把 Health Connect 中获准读取的数据交给你的个人 agent。只读，不修改记录；通过 USB 连接电脑，不向互联网发送健康数据。")
        status = text("正在检查 Health Connect…")
        button("1. 授予健康数据读取权限") {
            if (HealthConnectClient.getSdkStatus(this) == HealthConnectClient.SDK_AVAILABLE) request.launch(HealthReader.permissions)
            else status.text = "Health Connect 不可用，请先在系统设置中更新或启用。"
        }
        button("2. 允许后台读取（可选）") {
            if (HealthConnectClient.getSdkStatus(this) == HealthConnectClient.SDK_AVAILABLE && HealthReader(this).supportsBackground())
                request.launch(setOf(HealthPermission.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND))
            else status.text = "此设备暂不支持后台读取；查询时请保持本应用打开。"
        }
        button("3. 开启 USB 连接") {
            if (HealthConnectClient.getSdkStatus(this) == HealthConnectClient.SDK_AVAILABLE) {
                startForegroundService(Intent(this, BridgeService::class.java)); status.text = "USB 接口已启动。请在电脑上完成配对并检查连接。"
            }
        }
        button("停止连接") { stopService(Intent(this, BridgeService::class.java)); status.text = "连接已停止。" }
        text("配对口令（仅在你自己的电脑中输入）")
        text(prefs.getString("token", "") ?: "").apply { contentDescription = "vitaldock-pairing-token"; setTextIsSelectable(true) }
        button("查看隐私说明") { startActivity(Intent(this, PrivacyActivity::class.java)) }
        text("后台连接受安卓电量与运行时限影响；断开时重新打开应用并开启连接。撤销权限后，相应指标将不可读。")
        setContentView(ScrollView(this).apply { addView(column) })
        refresh()
    }
    private fun refresh() { lifecycleScope.launch {
        status.text = if (HealthConnectClient.getSdkStatus(this@MainActivity) == HealthConnectClient.SDK_AVAILABLE) {
            val permissions = HealthConnectClient.getOrCreate(this@MainActivity).permissionController.getGrantedPermissions()
            "Health Connect 可用；已授权 ${HealthReader.permissions.count { it in permissions }} / ${HealthReader.permissions.size} 类数据。"
        } else "Health Connect 不可用，请先在系统设置中启用或更新。"
    } }
}

class PrivacyActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(TextView(this).apply {
            textSize = 18f; setPadding(36, 48, 36, 36)
            text = "VitalDock 隐私说明\n\n仅在你授权后，读取所选 Health Connect 健康记录，供你自己的电脑和 agent 查询。\n\n应用不修改健康记录，不读取 GPS、通讯录或其他应用的文件，不上传到开发者服务器，不含统计分析或广告。\n\n接口只监听手机本机 127.0.0.1，通过你授权的 USB 调试转发。配对口令留在手机私有存储和你电脑的系统凭据库，不要分享口令。\n\n每次查询都会检查授权并读取手机数据库；缺失记录不会被填成零。多来源记录保留来源，不直接相加。\n\n你可以停止连接、在 Health Connect 中撤销授权或卸载应用。应用没有后台永久运行保证。"
        })
    }
}
