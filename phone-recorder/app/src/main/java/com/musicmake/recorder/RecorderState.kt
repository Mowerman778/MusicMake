package com.musicmake.recorder

import android.net.Uri
import android.os.Handler
import android.os.Looper

/** What the screen shows. The service writes it; the activity listens. Main thread only. */
object RecorderState {
    var recording = false
        private set
    var startedAtMs = 0L
        private set
    /** Recent peak level, 0..1, for the meter. */
    var level = 0f
        private set
    var lastName: String? = null
        private set
    var lastUri: Uri? = null
        private set
    /** An error or a hint to show under the button, or null. */
    var message: String? = null
        private set

    private val main = Handler(Looper.getMainLooper())
    private val listeners = mutableSetOf<() -> Unit>()

    fun listen(listener: () -> Unit) { listeners += listener }
    fun unlisten(listener: () -> Unit) { listeners -= listener }

    fun started() = post {
        recording = true
        startedAtMs = System.currentTimeMillis()
        level = 0f
        message = null
    }

    fun level(value: Float) = post { level = value }

    fun saved(name: String, uri: Uri, silent: Boolean) = post {
        recording = false
        level = 0f
        lastName = name
        lastUri = uri
        message = if (silent) {
            "The recording is silent. The app you played may block recording " +
                "(many streaming apps do), or nothing was playing."
        } else null
    }

    fun failed(error: String) = post {
        recording = false
        level = 0f
        message = error
    }

    private fun post(change: () -> Unit) {
        main.post {
            change()
            listeners.toList().forEach { it() }
        }
    }
}
