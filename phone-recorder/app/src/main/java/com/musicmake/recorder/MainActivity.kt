package com.musicmake.recorder

import android.Manifest
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.os.Build
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

class MainActivity : Activity() {

    private lateinit var status: TextView
    private lateinit var timer: TextView
    private lateinit var meter: ProgressBar
    private lateinit var record: Button
    private lateinit var quality: RadioGroup
    private lateinit var message: TextView
    private lateinit var lastBox: View
    private lateinit var lastName: TextView

    private val ticker = Handler(Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() {
            render()
            if (RecorderState.recording) ticker.postDelayed(this, 200)
        }
    }
    private val onChange: () -> Unit = {
        render()
        ticker.removeCallbacks(tick)
        if (RecorderState.recording) ticker.post(tick)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Android 15 draws apps edge to edge; keep content clear of the system bars.
        val root = requireViewById<View>(R.id.root)
        root.setOnApplyWindowInsetsListener { v, insets ->
            val bars = insets.getInsets(WindowInsets.Type.systemBars())
            v.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }

        status = requireViewById(R.id.status)
        timer = requireViewById(R.id.timer)
        meter = requireViewById(R.id.meter)
        record = requireViewById(R.id.record)
        quality = requireViewById(R.id.quality)
        message = requireViewById(R.id.message)
        lastBox = requireViewById(R.id.last_box)
        lastName = requireViewById(R.id.last_name)

        record.setOnClickListener {
            if (RecorderState.recording) RecordService.stop(this) else askToRecord()
        }
        requireViewById<Button>(R.id.play).setOnClickListener { openLast(Intent.ACTION_VIEW) }
        requireViewById<Button>(R.id.share).setOnClickListener { openLast(Intent.ACTION_SEND) }
    }

    override fun onStart() {
        super.onStart()
        RecorderState.listen(onChange)
        onChange()
    }

    override fun onStop() {
        RecorderState.unlisten(onChange)
        ticker.removeCallbacks(tick)
        super.onStop()
    }

    private fun askToRecord() {
        val needed = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= 33) add(Manifest.permission.POST_NOTIFICATIONS)
        }.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }

        if (needed.isEmpty()) askForCapture() else requestPermissions(needed.toTypedArray(), REQ_PERMISSIONS)
    }

    override fun onRequestPermissionsResult(code: Int, permissions: Array<out String>, results: IntArray) {
        if (code != REQ_PERMISSIONS) return
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            askForCapture()
        } else {
            toast("Android only lets apps record phone audio with the microphone permission.")
        }
    }

    /** Shows Android's "start recording or casting?" prompt. */
    private fun askForCapture() {
        val manager = getSystemService(MediaProjectionManager::class.java)!!
        @Suppress("DEPRECATION")
        startActivityForResult(manager.createScreenCaptureIntent(), REQ_CAPTURE)
    }

    override fun onActivityResult(code: Int, result: Int, data: Intent?) {
        if (code != REQ_CAPTURE) return
        if (result == RESULT_OK && data != null) {
            RecordService.start(this, result, data, selectedKbps())
        } else {
            toast("Recording cancelled.")
        }
    }

    private fun selectedKbps() = when (quality.checkedRadioButtonId) {
        R.id.q128 -> 128
        R.id.q320 -> 320
        else -> 192
    }

    private fun openLast(action: String) {
        val uri = RecorderState.lastUri ?: return
        val intent = Intent(action).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        if (action == Intent.ACTION_SEND) {
            intent.setType("audio/mpeg").putExtra(Intent.EXTRA_STREAM, uri)
        } else {
            intent.setDataAndType(uri, "audio/mpeg")
        }
        try {
            startActivity(if (action == Intent.ACTION_SEND) Intent.createChooser(intent, null) else intent)
        } catch (e: ActivityNotFoundException) {
            toast("No app found to open MP3 files.")
        }
    }

    private fun render() {
        val recording = RecorderState.recording
        status.text = if (recording) "Recording phone audio…" else "Ready"
        val seconds = if (recording) (System.currentTimeMillis() - RecorderState.startedAtMs) / 1000 else 0
        timer.text = "%d:%02d".format(seconds / 60, seconds % 60)
        meter.progress = (RecorderState.level * meter.max).toInt()
        record.text = if (recording) "Stop and save MP3" else "Start recording"
        for (i in 0 until quality.childCount) quality.getChildAt(i).isEnabled = !recording

        val msg = RecorderState.message
        message.visibility = if (msg == null) View.GONE else View.VISIBLE
        message.text = msg

        val name = RecorderState.lastName
        lastBox.visibility = if (name == null) View.GONE else View.VISIBLE
        lastName.text = name
    }

    private fun toast(text: String) = Toast.makeText(this, text, Toast.LENGTH_LONG).show()

    private companion object {
        const val REQ_PERMISSIONS = 1
        const val REQ_CAPTURE = 2
    }
}
