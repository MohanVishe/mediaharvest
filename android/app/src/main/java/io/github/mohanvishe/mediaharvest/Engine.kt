package io.github.mohanvishe.mediaharvest

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import android.webkit.MimeTypeMap
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import java.io.File
import java.util.Collections
import java.util.concurrent.ConcurrentHashMap

/** A link the engine may be given: http(s) only, one word, so it can never
 *  be read as a yt-dlp option. */
val LINK = Regex("""https?://[^\s<>"']+""", RegexOption.IGNORE_CASE)

/** yt-dlp with its own Python, FFmpeg and QuickJS (youtubedl-android). */
object Engine {
    @Volatile private var ready = false

    /** Unpacks Python and FFmpeg into the app's files on first use, which
     *  takes a few seconds once. */
    @Synchronized
    fun init(context: Context) {
        if (ready) return
        YoutubeDL.getInstance().init(context)
        FFmpeg.getInstance().init(context)
        ready = true
    }

    /** Runs one download into [dir]; throws on failure or cancel. */
    fun download(job: Job, dir: File, onProgress: (Float) -> Unit) {
        val r = YoutubeDLRequest(job.url)
        r.addOption("--no-playlist")
        r.addOption("--no-mtime")
        r.addOption("--embed-metadata")
        r.addOption("-P", dir.absolutePath)
        r.addOption("-o", "%(title).120B [%(id)s].%(ext)s")
        when (job.kind) {
            // The server's "mp4" choice: mp4 video with m4a audio, and plain
            // H.264 at equal height, so every phone plays it.
            Kind.VIDEO -> {
                val h = if (job.choice == "best") "" else "[height<=${job.choice}]"
                r.addOption("-f", "bv*$h[ext=mp4]+ba[ext=m4a]/b$h[ext=mp4]/bv*$h+ba/b$h/b")
                r.addOption("-S", "res,vcodec:h264,acodec:aac")
                r.addOption("--merge-output-format", "mp4")
            }
            Kind.AUDIO -> {
                r.addOption("-f", if (job.choice == "m4a") "ba[ext=m4a]/ba/b" else "ba/b")
                r.addOption("-x")
                r.addOption("--audio-format", job.choice)
                r.addOption("--audio-quality", "0")
                r.addOption("--embed-thumbnail")
                r.addOption("--convert-thumbnails", "jpg")
            }
        }
        if (job.id in cancelled) throw YoutubeDL.CanceledException()
        YoutubeDL.getInstance().execute(r, job.id) { progress, _, _ -> onProgress(progress) }
        if (job.id in cancelled) throw YoutubeDL.CanceledException()
    }

    /** Cancels may come before yt-dlp has started (the first download unpacks
     *  Python first), so they are remembered and checked around the run. */
    private val cancelled = Collections.newSetFromMap(ConcurrentHashMap<String, Boolean>())

    fun cancel(id: String) {
        cancelled += id
        YoutubeDL.getInstance().destroyProcessById(id)
    }

    fun forget(id: String) {
        cancelled -= id
    }

    /** Fetches the newest yt-dlp from its GitHub releases. Returns the new
     *  version, or null when already current. */
    fun update(context: Context): String? {
        init(context)
        val status = YoutubeDL.getInstance().updateYoutubeDL(context, YoutubeDL.UpdateChannel.STABLE)
        return if (status == YoutubeDL.UpdateStatus.DONE) version(context) else null
    }

    fun version(context: Context): String {
        init(context)
        return YoutubeDL.getInstance().version(context)
            ?: YoutubeDL.getInstance().execute(YoutubeDLRequest(emptyList<String>()).addOption("--version")).out.trim()
    }

    /** "Some title [id].mp4" (the -o template) -> "Some title". */
    fun titleOf(fileName: String) = fileName.substringBeforeLast('.').replace(Regex("""\s\[[^\]]+]$"""), "")

    /** The last "ERROR:" line yt-dlp printed, without the prefix. */
    fun reason(e: Throwable): String {
        val lines = (e.message ?: e.toString()).lines().map { it.trim() }.filter { it.isNotEmpty() }
        val line = lines.lastOrNull { it.startsWith("ERROR:") }?.removePrefix("ERROR:")?.trim() ?: lines.lastOrNull() ?: e.toString()
        return line.take(300)
    }
}

/** Adds finished files to Download/MediaHarvest, which needs no permission. */
object Library {
    private val folder = Environment.DIRECTORY_DOWNLOADS + "/MediaHarvest"

    fun save(context: Context, file: File): Saved {
        val mime = MimeTypeMap.getSingleton().getMimeTypeFromExtension(file.extension.lowercase()) ?: "application/octet-stream"
        val resolver = context.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, file.name)
            put(MediaStore.Downloads.MIME_TYPE, mime)
            put(MediaStore.Downloads.RELATIVE_PATH, folder)
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val uri: Uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: error("Android refused to add ${file.name} to Downloads")
        try {
            resolver.openOutputStream(uri)!!.use { out -> file.inputStream().use { it.copyTo(out) } }
            resolver.update(uri, ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }, null, null)
        } catch (e: Exception) {
            resolver.delete(uri, null, null)
            throw e
        }
        return Saved(uri.toString(), file.name, mime, file.length())
    }
}
