package com.musicmake.recorder

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.PI
import kotlin.math.sin

class TrimTest {
    @get:Rule val tmp = TemporaryFolder()

    private val rate = 48_000
    private val ch = 2

    /** [silenceBefore] s of silence, [tone] s of a loud tone, [silenceAfter] s of silence. */
    private fun recording(silenceBefore: Double, tone: Double, silenceAfter: Double): File {
        val a = (silenceBefore * rate).toInt()
        val b = a + (tone * rate).toInt()
        val total = b + (silenceAfter * rate).toInt()
        val buf = ByteBuffer.allocate(total * ch * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (i in 0 until total) {
            val v = if (i in a until b) (12000 * sin(2 * PI * 440 * i / rate)).toInt() else 0
            repeat(ch) { buf.putShort(v.toShort()) }
        }
        return tmp.newFile("rec.pcm").apply { writeBytes(buf.array()) }
    }

    @Test fun overviewHasOneBlockPer10ms() {
        val pcm = recording(1.0, 2.0, 1.5)
        val peaks = Trim.overview(pcm, ch)
        assertEquals(450, peaks.size)
        assertEquals(0f, peaks[50])
        assertTrue(peaks[200] > 0.3f)
    }

    @Test fun findSoundCutsLeadingAndTrailingSilence() {
        val pcm = recording(1.0, 2.0, 1.5)
        val total = Trim.frames(pcm, ch)
        val range = Trim.findSound(Trim.overview(pcm, ch), total, rate)!!
        assertEquals((0.9 * rate).toLong(), range.start)
        assertEquals((3.3 * rate).toLong(), range.end)
    }

    @Test fun findSoundKeepsEdgesWhenSoundStartsImmediately() {
        val pcm = recording(0.0, 1.0, 0.0)
        val total = Trim.frames(pcm, ch)
        assertEquals(Trim.Range(0, total), Trim.findSound(Trim.overview(pcm, ch), total, rate))
    }

    @Test fun findSoundIsNullForSilence() {
        val pcm = recording(2.0, 0.0, 0.0)
        assertNull(Trim.findSound(Trim.overview(pcm, ch), Trim.frames(pcm, ch), rate))
    }

    @Test fun exportWritesTheRangeWithFades() {
        val pcm = recording(1.0, 2.0, 1.0)
        val range = Trim.Range(rate.toLong(), 2L * rate) // 1 s of tone, cut on both sides
        val out = mutableListOf<Short>()
        var lastProgress = 0f
        Trim.export(pcm, ch, range, fadeFrames = 240, sink = { s, n ->
            for (i in 0 until n) out += s[i]
        }, progress = { lastProgress = it })
        assertEquals(rate * ch, out.size)
        assertEquals(0, out.first().toInt()) // faded in
        assertEquals(0, out.last().toInt()) // faded out
        assertEquals(1f, lastProgress)
    }

    @Test fun exportLeavesUntrimmedEdgesAlone() {
        val pcm = recording(0.0, 1.0, 0.0)
        val total = Trim.frames(pcm, ch)
        val out = ShortArray((total * ch).toInt())
        var at = 0
        Trim.export(pcm, ch, Trim.Range(0, total), fadeFrames = 240, sink = { s, n ->
            System.arraycopy(s, 0, out, at, n); at += n
        })
        val raw = ByteBuffer.wrap(pcm.readBytes()).order(ByteOrder.LITTLE_ENDIAN).asShortBuffer()
        val expected = ShortArray(raw.limit()).also { raw.get(it) }
        assertTrue(expected.contentEquals(out))
    }

    @Test fun trimmedExportEncodesToMp3() {
        val pcm = recording(1.0, 2.0, 1.0)
        val total = Trim.frames(pcm, ch)
        val range = Trim.findSound(Trim.overview(pcm, ch), total, rate)!!
        val bytes = ByteArrayOutputStream()
        Mp3Encoder(bytes, rate, ch, 192).use { mp3 ->
            Trim.export(pcm, ch, range, 240, sink = { s, n -> mp3.encode(s, n) })
        }
        val mp3 = bytes.toByteArray()
        // MPEG-1 Layer III frame sync, and roughly 2.4 s at 192 kbps.
        assertEquals(0xFF, mp3[0].toInt() and 0xFF)
        assertEquals(0xE0, mp3[1].toInt() and 0xE0)
        assertTrue(mp3.size in 50_000..65_000)
    }

    @Test fun formatsTimes() {
        assertEquals("0:00.0", Trim.format(0, rate))
        assertEquals("1:05.3", Trim.format((65.3 * rate).toLong(), rate))
    }
}
