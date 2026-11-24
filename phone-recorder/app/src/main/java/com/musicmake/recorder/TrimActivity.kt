package com.musicmake.recorder

import android.app.Activity
import android.app.AlertDialog
import android.app.NotificationManager
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.WindowInsets
import android.widget.Button
import android.widget.ProgressBar
import android.widget.RadioGroup
import android.widget.TextView
import android.widget.Toast
import java.io.BufferedOutputStream
import kotlin.math.max

/**
 * Trim the dead spots off the start and end of the last recording, then save it as an MP3.
 * The raw recording is only deleted once the MP3 is saved (or the user discards it).
 */
class TrimActivity : Activity() {
    private val rate = RecordService.SAMPLE_RATE
    private val channels = RecordService.CHANNELS

    private lateinit var waveform: WaveformView
    private lateinit var loading: ProgressBar
    private lateinit var startLabel: TextView
    private lateinit var endLabel: TextView
    private lateinit var lengthLabel: TextView
    private lateinit var message: TextView
    private lateinit var playStart: Button
    private lateinit var playEnd: Button
    private lateinit var quality: RadioGroup
    private lateinit var save: Button
    private lateinit var saveProgress: ProgressBar
    private lateinit var controls: List<View>

    private lateinit var preview: Preview
    private var peaks: FloatArray? = null
    private var playing = 0 // 0 none, 1 from start, 2 the ending
    private var saving = false

    private val main = Handler(Looper.getMainLooper())
    private val followPlayhead = object : Runnable {
        override fun run() {
            waveform.playhead = preview.position
            if (preview.playing) main.postDelayed(this, 50)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!Pending.exists(this)) {
            Toast.makeText(this, "There is no recording to trim.", Toast.LENGTH_LONG).show()
            finish()
            return
        }
        getSystemService(NotificationManager::class.java)?.cancel(RecordService.READY_NOTIFICATION_ID)
        setContentView(R.layout.activity_trim)
        requireViewById<View>(R.id.root).setOnApplyWindowInsetsListener { v, insets ->
            val bars = insets.getInsets(WindowInsets.Type.systemBars())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }

        waveform = requireViewById(R.id.waveform)
        loading = requireViewById(R.id.loading)
        startLabel = requireViewById(R.id.start_label)
        endLabel = requireViewById(R.id.end_label)
        lengthLabel = requireViewById(R.id.length_label)
        message = requireViewById(R.id.trim_message)
        playStart = requireViewById(R.id.play_start)
        playEnd = requireViewById(R.id.play_end)
        quality = requireViewById(R.id.quality)
        save = requireViewById(R.id.save)
        saveProgress = requireViewById(R.id.save_progress)
        requireViewById<TextView>(R.id.name).text = Pending.name(this)

        val pcm = Pending.audio(this)
        preview = Preview(pcm)

        val tenth = rate / 10L
        requireViewById<Button>(R.id.start_minus).setOnClickListener { nudge(-tenth, 0) }
        requireViewById<Button>(R.id.start_plus).setOnClickListener { nudge(tenth, 0) }
        requireViewById<Button>(R.id.end_minus).setOnClickListener { nudge(0, -tenth) }
        requireViewById<Button>(R.id.end_plus).setOnClickListener { nudge(0, tenth) }
        requireViewById<Button>(R.id.auto_trim).setOnClickListener { autoTrim(announce = true) }
        requireViewById<Button>(R.id.keep_all).setOnClickListener {
            stopPreview()
            waveform.setRange(0, waveform.totalFrames)
            message.visibility = View.GONE
            renderRange()
        }
        playStart.setOnClickListener { togglePreview(1) }
        playEnd.setOnClickListener { togglePreview(2) }
        save.setOnClickListener { saveMp3() }
        requireViewById<Button>(R.id.discard).setOnClickListener { confirmDiscard() }
        waveform.onChange = { _, _ ->
            stopPreview()
            renderRange()
        }

        val prefs = getSharedPreferences("settings", MODE_PRIVATE)
        quality.check(
            when (prefs.getInt("kbps", 192)) {
                128 -> R.id.q128
                320 -> R.id.q320
                else -> R.id.q192
            }
        )
        quality.setOnCheckedChangeListener { _, _ -> prefs.edit().putInt("kbps", kbps()).apply() }

        controls = listOf(
            R.id.start_minus, R.id.start_plus, R.id.end_minus, R.id.end_plus, R.id.auto_trim,
            R.id.keep_all, R.id.play_start, R.id.play_end, R.id.q128, R.id.q192, R.id.q320,
            R.id.save, R.id.discard, R.id.waveform,
        ).map { requireViewById<View>(it) }
        setEnabled(false)

        // Reading a long recording takes a moment; do it off the main thread.
        Thread({
            val total = Trim.frames(pcm, channels)
            val p = runCatching { Trim.overview(pcm, channels) }.getOrNull()
            runOnUiThread {
                if (isDestroyed) return@runOnUiThread
                loading.visibility = View.GONE
                if (p == null) {
                    showMessage("Could not read the recording.")
                    return@runOnUiThread
                }
                peaks = p
                waveform.setData(p, total)
                setEnabled(true)
                autoTrim(announce = false)
            }
        }, "overview").start()
    }

    override fun onStop() {
        stopPreview()
        super.onStop()
    }

    private fun kbps() = when (quality.checkedRadioButtonId) {
        R.id.q128 -> 128
        R.id.q320 -> 320
        else -> 192
    }

    /** Moves the handles to the first and last sound. */
    private fun autoTrim(announce: Boolean) {
        val p = peaks ?: return
        stopPreview()
        val range = Trim.findSound(p, waveform.totalFrames, rate)
        if (range == null) {
            waveform.setRange(0, waveform.totalFrames)
            showMessage(
                "No sound found: the recording is silent. The app you played may block " +
                    "recording (many streaming apps do), or nothing was playing."
            )
        } else {
            waveform.setRange(range.start, range.end)
            message.visibility = View.GONE
            if (announce && range.start == 0L && range.end == waveform.totalFrames) {
                Toast.makeText(this, "No dead spots found at the start or end.", Toast.LENGTH_SHORT).show()
            }
        }
        renderRange()
    }

    private fun nudge(startBy: Long, endBy: Long) {
        stopPreview()
        waveform.setRange(waveform.start + startBy, waveform.end + endBy)
        renderRange()
    }

    private fun renderRange() {
        startLabel.text = "Start  " + Trim.format(waveform.start, rate)
        endLabel.text = "End  " + Trim.format(waveform.end, rate)
        val cut = waveform.totalFrames - (waveform.end - waveform.start)
        lengthLabel.text = "Length " + Trim.format(waveform.end - waveform.start, rate) +
            if (cut > 0) "  (cutting " + Trim.format(cut, rate) + ")" else ""
    }

    private fun togglePreview(which: Int) {
        val was = playing
        stopPreview()
        if (was == which) return
        // "Play ending" plays the last 3 seconds before the end handle.
        val from = if (which == 1) waveform.start else max(waveform.start, waveform.end - 3L * rate)
        playing = which
        (if (which == 1) playStart else playEnd).text = getString(R.string.stop_preview)
        preview.play(from, waveform.end) { resetPreviewButtons() }
        main.post(followPlayhead)
    }

    private fun stopPreview() {
        if (!::preview.isInitialized) return
        preview.stop()
        resetPreviewButtons()
    }

    private fun resetPreviewButtons() {
        playing = 0
        main.removeCallbacks(followPlayhead)
        waveform.playhead = -1
        playStart.text = getString(R.string.play_start)
        playEnd.text = getString(R.string.play_end)
    }

    private fun saveMp3() {
        if (saving) return
        stopPreview()
        saving = true
        setEnabled(false)
        saveProgress.progress = 0
        saveProgress.visibility = View.VISIBLE
        save.text = getString(R.string.saving)

        val app = applicationContext
        val pcm = Pending.audio(app)
        val name = Pending.name(app)
        val range = Trim.Range(waveform.start, waveform.end)
        val kbps = kbps()
        var shown = -1
        // The save finishes even if this screen is closed meanwhile.
        Thread({
            try {
                val uri = Library.saveMp3(app, name) { out ->
                    Mp3Encoder(BufferedOutputStream(out, 64 * 1024), rate, channels, kbps).use { mp3 ->
                        Trim.export(pcm, channels, range, fadeFrames = rate / 200, // 5 ms fades
                            sink = { s, n -> mp3.encode(s, n) },
                            progress = { f ->
                                val p = (f * 1000).toInt()
                                if (p != shown) {
                                    shown = p
                                    runOnUiThread { saveProgress.progress = p }
                                }
                            })
                    }
                }
                Pending.discard(app)
                RecorderState.saved(name, uri)
                runOnUiThread {
                    Toast.makeText(app, "Saved $name", Toast.LENGTH_SHORT).show()
                    if (!isDestroyed) done()
                }
            } catch (e: Exception) {
                runOnUiThread {
                    if (isDestroyed) return@runOnUiThread
                    saving = false
                    setEnabled(true)
                    saveProgress.visibility = View.GONE
                    save.text = getString(R.string.save_mp3)
                    showMessage("Could not save the MP3: ${e.message}")
                }
            }
        }, "export").start()
    }

    private fun confirmDiscard() {
        AlertDialog.Builder(this)
            .setMessage("Delete this recording without saving it?")
            .setPositiveButton("Delete") { _, _ ->
                stopPreview()
                Pending.discard(this)
                done()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    /** Back to the main screen, which shows the saved file. */
    private fun done() {
        // Opened from the notification there is nothing underneath; open the main screen.
        if (isTaskRoot) startActivity(Intent(this, MainActivity::class.java))
        finish()
    }

    private fun setEnabled(enabled: Boolean) = controls.forEach { it.isEnabled = enabled }

    private fun showMessage(text: String) {
        message.text = text
        message.visibility = View.VISIBLE
    }
}
