package io.github.mohanvishe.mediaharvest

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import com.yausername.youtubedl_android.YoutubeDL
import java.io.File
import kotlin.concurrent.thread

/**
 * Runs the waiting downloads one at a time, with a progress notification so
 * Android keeps it alive while the screen is off or the app is closed.
 */
class DownloadService : Service() {
    private val main = Handler(Looper.getMainLooper())
    private var worker: Thread? = null
    private var current: String? = null
    private var lastNote = 0L

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Downloads.load(this)
        // Part-files of a download the system killed, which nothing will resume.
        val running = Downloads.jobs.value.filter { it.status == Status.RUNNING }.map { it.id }.toSet()
        File(cacheDir, "jobs").listFiles()?.filter { it.name !in running }?.forEach { it.deleteRecursively() }
        val channel = NotificationChannel(CHANNEL, getString(R.string.channel), NotificationManager.IMPORTANCE_LOW)
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTE_PROGRESS, note(getString(R.string.preparing), -1f), ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        if (worker?.isAlive != true) worker = thread(name = "downloads") { work() }
        return START_NOT_STICKY
    }

    /** Android 15 ends data-sync services after six hours a day. */
    override fun onTimeout(startId: Int, fgsType: Int) {
        current?.let { Engine.cancel(it) }
        stopSelf()
    }

    private fun work() {
        while (true) {
            val job = Downloads.claimNext() ?: break
            current = job.id
            run(job)
            current = null
        }
        // On the main thread, like onStartCommand, so a download added
        // just now is either picked up here or by a new worker.
        main.post {
            if (Downloads.busy()) {
                worker = thread(name = "downloads") { work() }
            } else {
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }
    }

    private fun run(job: Job) {
        val dir = File(cacheDir, "jobs/${job.id}")
        dir.deleteRecursively()
        dir.mkdirs()
        val label = job.title.ifEmpty { job.url }
        try {
            notify(NOTE_PROGRESS, note(label, -1f))
            Engine.init(applicationContext)
            Engine.download(job, dir) { p ->
                Downloads.progress(job.id, p)
                val now = SystemClock.elapsedRealtime()
                if (now - lastNote > 1000) {
                    lastNote = now
                    notify(NOTE_PROGRESS, note(label, p))
                }
            }
            val files = dir.listFiles().orEmpty().filter { it.isFile && !it.name.startsWith(".") }.sortedBy { it.name }
            check(files.isNotEmpty()) { "yt-dlp finished without a file" }
            val saved = files.map { Library.save(this, it) }
            val title = Engine.titleOf(saved.first().name)
            Downloads.update(job.id) { it.copy(status = Status.DONE, progress = 100f, title = title, files = saved) }
            notify(NOTE_DONE, done(getString(R.string.note_saved, title)))
        } catch (e: YoutubeDL.CanceledException) {
            Downloads.update(job.id) { it.copy(status = Status.STOPPED, progress = -1f) }
        } catch (e: Throwable) {
            // Errors too (a broken engine file, out of memory): one failed
            // download must not take the app down.
            val reason = Engine.reason(e)
            Downloads.update(job.id) { it.copy(status = Status.FAILED, progress = -1f, error = reason) }
            notify(NOTE_DONE, done(getString(R.string.note_failed, label)))
        } finally {
            dir.deleteRecursively()
            Engine.forget(job.id)
        }
    }

    private fun notify(id: Int, n: Notification) = getSystemService(NotificationManager::class.java).notify(id, n)

    private fun openApp() = PendingIntent.getActivity(
        this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE,
    )

    private fun note(text: String, progress: Float): Notification = Notification.Builder(this, CHANNEL)
        .setSmallIcon(R.drawable.ic_download)
        .setContentTitle(getString(R.string.note_title))
        .setContentText(text)
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .setContentIntent(openApp())
        .setProgress(100, progress.toInt().coerceIn(0, 100), progress < 0)
        .build()

    private fun done(text: String): Notification = Notification.Builder(this, CHANNEL)
        .setSmallIcon(R.drawable.ic_download)
        .setContentTitle(text)
        .setAutoCancel(true)
        .setContentIntent(openApp())
        .build()

    companion object {
        private const val CHANNEL = "downloads"
        private const val NOTE_PROGRESS = 1
        private const val NOTE_DONE = 2

        fun start(context: Context) = context.startForegroundService(Intent(context, DownloadService::class.java))
    }
}
