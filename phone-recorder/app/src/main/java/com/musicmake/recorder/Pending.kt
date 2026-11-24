package com.musicmake.recorder

import android.content.Context
import java.io.File

/**
 * The recording waiting to be trimmed and saved: raw 48 kHz stereo 16-bit PCM in app storage.
 * It stays until it is saved as an MP3 or discarded, so a closed app loses nothing.
 */
object Pending {
    private fun dir(context: Context) = File(context.filesDir, "pending")
    fun audio(context: Context) = File(dir(context), "audio.pcm")
    private fun nameFile(context: Context) = File(dir(context), "name.txt")

    /** Starts a new pending recording, replacing any old one. Returns the file to write. */
    fun begin(context: Context, name: String): File {
        dir(context).deleteRecursively()
        dir(context).mkdirs()
        nameFile(context).writeText(name)
        return audio(context)
    }

    /** True when a finished recording is waiting. */
    fun exists(context: Context) =
        !RecorderState.recording && audio(context).length() >= 2 * RecordService.CHANNELS

    fun name(context: Context): String =
        nameFile(context).takeIf { it.exists() }?.readText() ?: "Recording.mp3"

    fun discard(context: Context) {
        dir(context).deleteRecursively()
    }
}
