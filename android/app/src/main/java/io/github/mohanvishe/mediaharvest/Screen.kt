package io.github.mohanvishe.mediaharvest

import android.text.format.Formatter
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.roundToInt

private val VIDEO_CHOICES = listOf("best", "1080", "720", "480")
private val AUDIO_CHOICES = listOf("m4a", "mp3")

/** The one screen: a link box, two choices, the download list. Content is
 *  capped at 720dp so tablets and landscape phones get a readable column. */
@Composable
fun Screen(app: MainActivity) {
    val context = LocalContext.current
    val jobs by Downloads.jobs.collectAsState()
    var url by rememberSaveable { mutableStateOf("") }
    var badLink by rememberSaveable { mutableStateOf(false) }
    var kind by rememberSaveable { mutableStateOf(app.choices.getString("kind", Kind.VIDEO.name)!!) }
    var video by rememberSaveable { mutableStateOf(app.choices.getString("video", "best")!!) }
    var audio by rememberSaveable { mutableStateOf(app.choices.getString("audio", "m4a")!!) }
    var updating by remember { mutableStateOf(false) }
    var about by rememberSaveable { mutableStateOf(false) }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    val incoming = app.incoming.value
    LaunchedEffect(incoming) {
        if (incoming != null) {
            url = incoming
            badLink = false
            app.incoming.value = null
        }
    }

    fun submit() {
        val isVideo = kind == Kind.VIDEO.name
        badLink = !app.download(url, Kind.valueOf(kind), if (isVideo) video else audio)
        if (!badLink) {
            url = ""
            app.choices.edit().putString("kind", kind).putString("video", video).putString("audio", audio).apply()
        }
    }

    fun updateEngine() {
        if (Downloads.busy()) {
            scope.launch { snackbar.showSnackbar(context.getString(R.string.update_busy)) }
            return
        }
        updating = true
        scope.launch {
            launch { snackbar.showSnackbar(context.getString(R.string.updating)) }
            val result = withContext(Dispatchers.IO) { runCatching { Engine.update(context.applicationContext) } }
            updating = false
            snackbar.currentSnackbarData?.dismiss()
            snackbar.showSnackbar(
                result.fold(
                    { v -> if (v == null) context.getString(R.string.up_to_date) else context.getString(R.string.updated, v) },
                    { e -> context.getString(R.string.update_failed, Engine.reason(e)) },
                ),
            )
        }
    }

    Scaffold(
        topBar = { TopBar(updating, onUpdate = ::updateEngine, onAbout = { about = true }) },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = MaterialTheme.colorScheme.background,
    ) { pad ->
        Box(Modifier.fillMaxSize().padding(pad).consumeWindowInsets(pad).imePadding(), contentAlignment = Alignment.TopCenter) {
            LazyColumn(
                Modifier.widthIn(max = 720.dp).fillMaxWidth(),
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(
                            value = url,
                            onValueChange = { url = it; badLink = false },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            placeholder = { Text(stringResource(R.string.link_hint)) },
                            isError = badLink,
                            supportingText = if (badLink) ({ Text(stringResource(R.string.bad_link)) }) else null,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Go),
                            keyboardActions = KeyboardActions(onGo = { submit() }),
                            trailingIcon = {
                                TextButton(onClick = { app.paste()?.let { url = it; badLink = false } }) { Text(stringResource(R.string.paste)) }
                            },
                        )
                        Choice(
                            listOf(Kind.VIDEO.name to stringResource(R.string.video), Kind.AUDIO.name to stringResource(R.string.audio)),
                            kind,
                        ) { kind = it }
                        if (kind == Kind.VIDEO.name) {
                            Choice(VIDEO_CHOICES.map { it to label(Kind.VIDEO, it) }, video) { video = it }
                        } else {
                            Choice(AUDIO_CHOICES.map { it to label(Kind.AUDIO, it) }, audio) { audio = it }
                        }
                        Button(
                            onClick = ::submit, enabled = !updating, shape = MaterialTheme.shapes.small,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        ) {
                            Icon(painterResource(R.drawable.ic_download), null, Modifier.size(18.dp))
                            Spacer(Modifier.width(8.dp))
                            Text(stringResource(R.string.download))
                        }
                    }
                }
                item {
                    Row(Modifier.fillMaxWidth().padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            stringResource(R.string.downloads), Modifier.weight(1f),
                            style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        if (jobs.any { it.status != Status.QUEUED && it.status != Status.RUNNING }) {
                            TextButton(onClick = Downloads::clearFinished) { Text(stringResource(R.string.clear)) }
                        }
                    }
                }
                if (jobs.isEmpty()) {
                    item {
                        Text(
                            stringResource(R.string.empty),
                            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                items(jobs, key = { it.id }) { JobRow(it, app) }
            }
        }
    }

    if (about) About(app) { about = false }
}

private fun label(kind: Kind, choice: String) = when {
    kind == Kind.AUDIO -> choice.uppercase()
    choice == "best" -> "Best"
    else -> "${choice}p"
}

@Composable
private fun TopBar(updating: Boolean, onUpdate: () -> Unit, onAbout: () -> Unit) {
    var menu by remember { mutableStateOf(false) }
    Box(
        Modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.safeDrawing.only(WindowInsetsSides.Top + WindowInsetsSides.Horizontal)),
        contentAlignment = Alignment.Center,
    ) {
        Row(
            Modifier.widthIn(max = 720.dp).fillMaxWidth().height(56.dp).padding(start = 16.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("mediaharvest", Modifier.weight(1f), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Medium)
            Box {
                IconButton(onClick = { menu = true }) { Icon(painterResource(R.drawable.ic_more), stringResource(R.string.more)) }
                DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                    DropdownMenuItem(
                        text = { Text(stringResource(R.string.update_engine)) },
                        onClick = { menu = false; onUpdate() },
                        enabled = !updating,
                    )
                    DropdownMenuItem(text = { Text(stringResource(R.string.about)) }, onClick = { menu = false; onAbout() })
                }
            }
        }
    }
}

/** A row of equal segments, one picked: Video/Audio, a quality, a format. */
@Composable
private fun Choice(options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit) {
    val colors = MaterialTheme.colorScheme
    val shape = MaterialTheme.shapes.small
    Row(Modifier.fillMaxWidth().border(1.dp, colors.outlineVariant, shape).selectableGroup()) {
        options.forEach { (id, text) ->
            val on = id == selected
            Box(
                Modifier.weight(1f).heightIn(min = 44.dp)
                    .background(if (on) colors.onBackground else Color.Transparent, shape)
                    .selectable(selected = on, role = Role.RadioButton) { onSelect(id) },
                contentAlignment = Alignment.Center,
            ) {
                Text(text, style = MaterialTheme.typography.labelLarge, color = if (on) colors.background else colors.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun JobRow(job: Job, app: MainActivity) {
    val colors = MaterialTheme.colorScheme
    val shape = MaterialTheme.shapes.medium
    Row(
        Modifier.fillMaxWidth().background(colors.surface, shape).border(1.dp, colors.outlineVariant, shape)
            .padding(start = 12.dp, top = 10.dp, bottom = 10.dp, end = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            painterResource(if (job.kind == Kind.VIDEO) R.drawable.ic_video else R.drawable.ic_music), null,
            Modifier.size(20.dp), tint = colors.onSurfaceVariant,
        )
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(job.title.ifEmpty { job.url }, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
            val small = MaterialTheme.typography.bodySmall
            when (job.status) {
                Status.RUNNING -> Row(verticalAlignment = Alignment.CenterVertically) {
                    Blocks(job.progress, Modifier.weight(1f).height(8.dp))
                    Text(
                        if (job.progress >= 0) "${job.progress.roundToInt()}%" else stringResource(R.string.preparing),
                        Modifier.padding(start = 8.dp), style = small, color = colors.onSurfaceVariant,
                    )
                }
                Status.QUEUED -> Text(stringResource(R.string.queued), style = small, color = colors.onSurfaceVariant)
                Status.STOPPED -> Text(stringResource(R.string.stopped), style = small, color = colors.onSurfaceVariant)
                Status.FAILED -> Text(
                    stringResource(R.string.failed) + ": " + job.error,
                    style = small, color = colors.error, maxLines = 3, overflow = TextOverflow.Ellipsis,
                )
                Status.DONE -> Text(
                    listOf(
                        if (job.files.size == 1) job.files[0].name.substringAfterLast('.') else "${job.files.size} files",
                        Formatter.formatShortFileSize(LocalContext.current, job.files.sumOf { it.size }),
                        label(job.kind, job.choice),
                    ).joinToString(" · "),
                    style = small, color = colors.onSurfaceVariant,
                )
            }
        }
        when (job.status) {
            Status.DONE -> {
                Action(R.drawable.ic_open, R.string.open) { app.open(job.files.first()) }
                Action(R.drawable.ic_close, R.string.remove) { Downloads.remove(job.id) }
            }
            Status.QUEUED, Status.RUNNING -> Action(R.drawable.ic_close, R.string.cancel) { app.cancel(job) }
            Status.FAILED, Status.STOPPED -> {
                Action(R.drawable.ic_reload, R.string.retry) { app.retry(job) }
                Action(R.drawable.ic_close, R.string.remove) { Downloads.remove(job.id) }
            }
        }
    }
}

@Composable
private fun Action(icon: Int, text: Int, onClick: () -> Unit) {
    IconButton(onClick = onClick) { Icon(painterResource(icon), stringResource(text), Modifier.size(20.dp)) }
}

/** Progress drawn in blocks, as in the web app's Mono theme. While the size
 *  is unknown, a short run of blocks moves across. */
@Composable
private fun Blocks(progress: Float, modifier: Modifier) {
    val on = MaterialTheme.colorScheme.primary
    val off = MaterialTheme.colorScheme.outlineVariant
    val count = 24
    val sweep by rememberInfiniteTransition(label = "blocks").animateFloat(
        0f, count.toFloat(), infiniteRepeatable(tween(1600, easing = LinearEasing), RepeatMode.Restart), label = "sweep",
    )
    Canvas(modifier) {
        val gap = 2.dp.toPx()
        val w = (size.width - gap * (count - 1)) / count
        val filled = (progress / 100f * count).roundToInt()
        for (i in 0 until count) {
            val lit = if (progress >= 0) i < filled else (i - sweep.toInt() + count) % count < 4
            drawRect(if (lit) on else off, Offset(i * (w + gap), 0f), Size(w, size.height))
        }
    }
}

@Composable
private fun About(app: MainActivity, onClose: () -> Unit) {
    var engine by remember { mutableStateOf("…") }
    LaunchedEffect(Unit) {
        engine = withContext(Dispatchers.IO) { runCatching { Engine.version(app.applicationContext) }.getOrDefault("?") }
    }
    AlertDialog(
        onDismissRequest = onClose,
        confirmButton = { TextButton(onClick = onClose) { Text(stringResource(R.string.close)) } },
        dismissButton = { TextButton(onClick = app::openSource) { Text(stringResource(R.string.source)) } },
        title = { Text(stringResource(R.string.app_name)) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(stringResource(R.string.about_version, app.appVersion(), engine))
                Text(stringResource(R.string.about_privacy))
                Text(stringResource(R.string.about_licences), style = MaterialTheme.typography.bodySmall)
            }
        },
    )
}
