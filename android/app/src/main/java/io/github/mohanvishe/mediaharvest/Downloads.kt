package io.github.mohanvishe.mediaharvest

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

enum class Kind { VIDEO, AUDIO }

enum class Status { QUEUED, RUNNING, DONE, FAILED, STOPPED }

/** A file added to Download/MediaHarvest. */
data class Saved(val uri: String, val name: String, val mime: String, val size: Long)

/**
 * One download. [choice] is a video height ("best", "1080", ...) or an audio
 * format ("m4a", "mp3"). [progress] runs 0..100, or is -1 while unknown.
 */
data class Job(
    val id: String,
    val url: String,
    val kind: Kind,
    val choice: String,
    val status: Status = Status.QUEUED,
    val title: String = "",
    val progress: Float = -1f,
    val error: String = "",
    val files: List<Saved> = emptyList(),
)

/**
 * The download list, newest first, kept in the app's private files as JSON.
 * The screen and the download service share it within one process.
 */
object Downloads {
    private const val KEEP = 200

    private val state = MutableStateFlow<List<Job>>(emptyList())
    val jobs: StateFlow<List<Job>> = state
    private var file: File? = null

    /** Reads the list once per process. A download that was running when the
     *  process died cannot resume, so it shows as stopped, with Retry. */
    @Synchronized
    fun load(context: Context) {
        if (file != null) return
        val f = File(context.filesDir, "downloads.json")
        file = f
        state.value = runCatching { fromJson(JSONArray(f.readText())) }.getOrDefault(emptyList())
            .map { if (it.status == Status.QUEUED || it.status == Status.RUNNING) it.copy(status = Status.STOPPED, progress = -1f) else it }
    }

    fun add(job: Job) = edit { listOf(job) + it.take(KEEP - 1) }

    fun update(id: String, change: (Job) -> Job) = edit { list -> list.map { if (it.id == id) change(it) else it } }

    /** Progress changes many times a second, so it is not written to disk. */
    fun progress(id: String, progress: Float) =
        edit(save = false) { list -> list.map { if (it.id == id) it.copy(progress = progress) else it } }

    fun remove(id: String) = edit { list -> list.filterNot { it.id == id } }

    fun clearFinished() = edit { list -> list.filter { it.status == Status.QUEUED || it.status == Status.RUNNING } }

    fun busy() = state.value.any { it.status == Status.QUEUED || it.status == Status.RUNNING }

    /** Marks the oldest waiting job as running and returns it. */
    @Synchronized
    fun claimNext(): Job? {
        val next = state.value.lastOrNull { it.status == Status.QUEUED } ?: return null
        update(next.id) { it.copy(status = Status.RUNNING, progress = -1f, error = "") }
        return next
    }

    @Synchronized
    private fun edit(save: Boolean = true, change: (List<Job>) -> List<Job>) {
        val next = change(state.value)
        state.value = next
        // A full phone must not crash a tap; the list stays right in memory.
        if (save) file?.let { runCatching { write(it, next) } }
    }

    private fun write(f: File, jobs: List<Job>) {
        val tmp = File(f.parentFile, f.name + ".tmp")
        tmp.writeText(toJson(jobs).toString())
        tmp.renameTo(f)
    }

    private fun toJson(jobs: List<Job>) = JSONArray().apply {
        jobs.forEach { j ->
            put(JSONObject()
                .put("id", j.id).put("url", j.url).put("kind", j.kind.name).put("choice", j.choice)
                .put("status", j.status.name).put("title", j.title).put("error", j.error)
                .put("files", JSONArray().apply {
                    j.files.forEach { put(JSONObject().put("uri", it.uri).put("name", it.name).put("mime", it.mime).put("size", it.size)) }
                }))
        }
    }

    private fun fromJson(a: JSONArray) = (0 until a.length()).map { i ->
        val o = a.getJSONObject(i)
        val files = o.optJSONArray("files") ?: JSONArray()
        Job(
            id = o.getString("id"), url = o.getString("url"),
            kind = Kind.valueOf(o.getString("kind")), choice = o.getString("choice"),
            status = Status.valueOf(o.getString("status")), title = o.optString("title"),
            progress = if (o.getString("status") == Status.DONE.name) 100f else -1f,
            error = o.optString("error"),
            files = (0 until files.length()).map { k ->
                val s = files.getJSONObject(k)
                Saved(s.getString("uri"), s.getString("name"), s.getString("mime"), s.optLong("size"))
            },
        )
    }
}
