package com.musicmake.recorder

import java.io.BufferedInputStream
import java.io.File
import java.io.FileInputStream
import java.io.InputStream
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Trimming for raw recordings: 16-bit little-endian interleaved PCM files.
 * No Android classes here, so it is unit-tested on a plain JVM.
 */
object Trim {
    /** Frames per overview block: 10 ms at 48 kHz. */
    const val BLOCK_FRAMES = 480

    /** About -50 dBFS. Quieter than this counts as a dead spot. */
    const val SILENCE = 0.003f

    data class Range(val start: Long, val end: Long) {
        val frames get() = end - start
    }

    fun frames(pcm: File, channels: Int): Long = pcm.length() / (2 * channels)

    /** Peak level (0..1) of each [BLOCK_FRAMES]-frame block of the file. */
    fun overview(pcm: File, channels: Int): FloatArray {
        val total = frames(pcm, channels)
        val peaks = FloatArray(((total + BLOCK_FRAMES - 1) / BLOCK_FRAMES).toInt())
        val blockSamples = BLOCK_FRAMES * channels
        val buf = ByteArray(blockSamples * 2 * 200) // 2 s per read, whole blocks only
        var block = 0
        BufferedInputStream(FileInputStream(pcm)).use { input ->
            while (block < peaks.size) {
                val n = readFully(input, buf)
                if (n <= 0) break
                val samples = ByteBuffer.wrap(buf, 0, n - n % 2)
                    .order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
                var i = 0
                while (i < samples.limit() && block < peaks.size) {
                    val end = min(i + blockSamples, samples.limit())
                    var peak = 0
                    for (j in i until end) peak = max(peak, abs(samples.get(j).toInt()))
                    peaks[block++] = peak / 32768f
                    i = end
                }
            }
        }
        return peaks
    }

    /**
     * The part of the recording between the first and last sound louder than [threshold],
     * with a little padding, or null if the whole recording is quiet.
     */
    fun findSound(
        peaks: FloatArray,
        totalFrames: Long,
        sampleRate: Int,
        threshold: Float = SILENCE,
        padBeforeMs: Int = 100,
        padAfterMs: Int = 300,
    ): Range? {
        val first = peaks.indexOfFirst { it > threshold }
        if (first < 0) return null
        val last = peaks.indexOfLast { it > threshold }
        val start = max(0L, first.toLong() * BLOCK_FRAMES - sampleRate.toLong() * padBeforeMs / 1000)
        val end = min(totalFrames, (last + 1L) * BLOCK_FRAMES + sampleRate.toLong() * padAfterMs / 1000)
        return Range(start, end)
    }

    /**
     * Streams frames [range] of [pcm] to [sink] in chunks (interleaved samples, count),
     * with short fades at cut points so trimmed edges don't click.
     */
    fun export(
        pcm: File,
        channels: Int,
        range: Range,
        fadeFrames: Int,
        sink: (ShortArray, Int) -> Unit,
        progress: (Float) -> Unit = {},
    ) {
        val total = frames(pcm, channels)
        require(range.start in 0..range.end && range.end <= total) { "bad range $range of $total" }
        val fadeIn = range.start > 0
        val fadeOut = range.end < total
        val frameBytes = 2 * channels
        val chunk = 4800
        val bytes = ByteArray(chunk * frameBytes)
        val samples = ShortArray(chunk * channels)
        RandomAccessFile(pcm, "r").use { file ->
            file.seek(range.start * frameBytes)
            var pos = range.start
            while (pos < range.end) {
                val n = min(chunk.toLong(), range.end - pos).toInt()
                file.readFully(bytes, 0, n * frameBytes)
                ByteBuffer.wrap(bytes, 0, n * frameBytes).order(ByteOrder.LITTLE_ENDIAN)
                    .asShortBuffer().get(samples, 0, n * channels)
                for (k in 0 until n) {
                    val frame = pos + k
                    var gain = 1f
                    if (fadeIn && frame - range.start < fadeFrames) {
                        gain = (frame - range.start).toFloat() / fadeFrames
                    }
                    if (fadeOut && range.end - 1 - frame < fadeFrames) {
                        gain = min(gain, (range.end - 1 - frame).toFloat() / fadeFrames)
                    }
                    if (gain < 1f) {
                        for (c in 0 until channels) {
                            val i = k * channels + c
                            samples[i] = (samples[i] * gain).toInt().toShort()
                        }
                    }
                }
                sink(samples, n * channels)
                pos += n
                progress((pos - range.start).toFloat() / max(1L, range.frames))
            }
        }
    }

    /** "1:05.3" for a position in frames. */
    fun format(frames: Long, sampleRate: Int): String {
        val tenths = frames * 10 / sampleRate
        return "%d:%02d.%d".format(tenths / 600, tenths / 10 % 60, tenths % 10)
    }

    private fun readFully(input: InputStream, buf: ByteArray): Int {
        var total = 0
        while (total < buf.size) {
            val n = input.read(buf, total, buf.size - total)
            if (n < 0) break
            total += n
        }
        return total
    }
}
