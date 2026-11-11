package io.github.mohanvishe.mediaharvest

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.mutableStateOf
import java.util.UUID

class MainActivity : ComponentActivity() {
    /** A link shared from another app, waiting for the screen to take it. */
    val incoming = mutableStateOf<String?>(null)
    val choices by lazy { getSharedPreferences("choices", MODE_PRIVATE) }
    private val askNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        Downloads.load(this)
        if (savedInstanceState == null) incoming.value = sharedLink(intent)
        setContent { MonoTheme { Screen(this) } }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        sharedLink(intent)?.let { incoming.value = it }
    }

    private fun sharedLink(intent: Intent?): String? =
        if (intent?.action == Intent.ACTION_SEND) intent.getStringExtra(Intent.EXTRA_TEXT)?.let { LINK.find(it)?.value } else null

    /** Reads the clipboard only when Paste is tapped. */
    fun paste(): String? {
        val clip = getSystemService(ClipboardManager::class.java).primaryClip ?: return null
        if (clip.itemCount == 0) return null
        val text = clip.getItemAt(0).coerceToText(this).toString()
        return LINK.find(text)?.value ?: text.trim()
    }

    /** Queues a download; false when [url] is not a single http(s) link. */
    fun download(url: String, kind: Kind, choice: String): Boolean {
        val link = url.trim()
        if (!LINK.matches(link)) return false
        Downloads.add(Job(UUID.randomUUID().toString(), link, kind, choice))
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        DownloadService.start(this)
        return true
    }

    fun retry(job: Job) {
        Downloads.update(job.id) { if (it.status == Status.FAILED || it.status == Status.STOPPED) it.copy(status = Status.QUEUED, error = "") else it }
        DownloadService.start(this)
    }

    fun cancel(job: Job) {
        Downloads.update(job.id) { if (it.status == Status.QUEUED) it.copy(status = Status.STOPPED) else it }
        if (job.status == Status.RUNNING) Engine.cancel(job.id)
    }

    fun open(file: Saved) = view(Uri.parse(file.uri), file.mime)

    fun openSource() = view(Uri.parse(SOURCE), null)

    private fun view(uri: Uri, mime: String?) {
        val intent = Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        try {
            startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            Toast.makeText(this, R.string.no_app, Toast.LENGTH_SHORT).show()
        }
    }

    fun appVersion(): String = packageManager.getPackageInfo(packageName, 0).versionName ?: ""

    companion object {
        const val SOURCE = "https://github.com/MohanVishe/mediaharvest"
    }
}
