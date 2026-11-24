package com.musicmake.recorder

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import android.os.Handler
import android.os.Looper
import java.io.File
import java.io.RandomAccessFile
import java.util.concurrent.atomic.AtomicBoolean

/** Plays part of the raw recording so the trim points can be checked by ear. */
class Preview(private val pcm: File) {
    private val rate = RecordService.SAMPLE_RATE
    private val channels = RecordService.CHANNELS
    private val main = Handler(Looper.getMainLooper())
    private var thread: Thread? = null
    private var cancel = AtomicBoolean(true)
    @Volatile private var track: AudioTrack? = null
    @Volatile private var from = 0L

    val playing get() = thread != null

    /** The frame being heard now, or -1 when not playing. */
    val position: Long
        get() = track?.let { t -> runCatching { from + t.playbackHeadPosition }.getOrNull() } ?: -1

    fun play(start: Long, end: Long, onDone: () -> Unit) {
        stop()
        val stopped = AtomicBoolean(false)
        cancel = stopped
        from = start
        lateinit var me: Thread
        me = Thread({
            val minBuffer = AudioTrack.getMinBufferSize(
                rate, AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_16BIT
            )
            val t = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(rate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                        .build()
                )
                .setTransferMode(AudioTrack.MODE_STREAM)
                .setBufferSizeInBytes(minBuffer * 2)
                .build()
            track = t
            try {
                val frameBytes = 2 * channels
                val buf = ByteArray(4800 * frameBytes)
                RandomAccessFile(pcm, "r").use { file ->
                    file.seek(start * frameBytes)
                    t.play()
                    var pos = start
                    while (!stopped.get() && pos < end) {
                        val n = minOf(4800L, end - pos).toInt()
                        file.readFully(buf, 0, n * frameBytes)
                        t.write(buf, 0, n * frameBytes)
                        pos += n
                    }
                    // Let the buffered tail finish playing.
                    while (!stopped.get() && t.playbackHeadPosition < pos - start) Thread.sleep(20)
                }
            } catch (_: Exception) {
            } finally {
                if (track === t) track = null
                t.release()
                main.post {
                    // A stopped or replaced preview reports nothing.
                    if (thread === me) {
                        thread = null
                        onDone()
                    }
                }
            }
        }, "preview")
        thread = me
        me.start()
    }

    /** Stops playback. The onDone of the stopped preview is not called. */
    fun stop() {
        cancel.set(true)
        val t = thread
        thread = null
        t?.join(500)
    }
}
