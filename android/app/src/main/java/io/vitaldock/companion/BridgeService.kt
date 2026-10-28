package io.vitaldock.companion

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.IBinder

class BridgeService : Service() {
    private var server: BridgeServer? = null
    override fun onBind(intent: Intent?): IBinder? = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val token = getSharedPreferences("pairing", MODE_PRIVATE).getString("token", null)
        if (token == null || token.length != 64) { stopSelf(); return START_NOT_STICKY }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("usb", "VitalDock USB 连接", NotificationManager.IMPORTANCE_LOW))
        startForeground(1, Notification.Builder(this, "usb").setContentTitle("VitalDock 健康连接")
            .setContentText("已开启本机只读接口，可在应用中停止")
            .setSmallIcon(android.R.drawable.stat_notify_sync).build())
        try {
            server?.stop()
            server = BridgeServer(this, token).apply { start(30000, true) }
        } catch (_: Exception) { stopSelf() }
        return START_NOT_STICKY
    }
    override fun onTimeout(startId: Int, fgsType: Int) { stopSelf() }
    override fun onDestroy() { server?.stop(); server = null; super.onDestroy() }
}
