package com.musicmake.recorder

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import kotlin.math.abs
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min

/**
 * The recording's waveform with two draggable handles: where the kept part starts and ends.
 * The trimmed-away parts are dimmed.
 */
class WaveformView(context: Context, attrs: AttributeSet?) : View(context, attrs) {
    private var peaks = FloatArray(0)
    var totalFrames = 0L
        private set
    var start = 0L
        private set
    var end = 0L
        private set
    /** Preview position in frames, or -1. */
    var playhead = -1L
        set(value) { field = value; invalidate() }

    /** Called while a handle is dragged, with the new start and end. */
    var onChange: ((Long, Long) -> Unit)? = null

    private val minGap get() = RecordService.SAMPLE_RATE / 2L // keep at least 0.5 s
    private val density = resources.displayMetrics.density
    private var dragging = 0 // 0 none, 1 start, 2 end

    private val accent: Int
    private val text: Int
    init {
        val a = context.obtainStyledAttributes(
            intArrayOf(android.R.attr.colorAccent, android.R.attr.textColorPrimary)
        )
        accent = a.getColor(0, 0xFF3B82F6.toInt())
        text = a.getColor(1, 0xFF888888.toInt())
        a.recycle()
        isClickable = true
    }

    private val wave = Paint().apply { color = accent; strokeWidth = 1f * density }
    private val dim = Paint().apply { color = text; alpha = 70 }
    private val handle = Paint().apply { color = text; strokeWidth = 3f * density; isAntiAlias = true }
    private val head = Paint().apply { color = 0xFFEF4444.toInt(); strokeWidth = 2f * density }
    private val centre = Paint().apply { color = text; alpha = 40; strokeWidth = 1f * density }

    fun setData(peaks: FloatArray, totalFrames: Long) {
        this.peaks = peaks
        this.totalFrames = totalFrames
        setRange(0, totalFrames)
    }

    fun setRange(start: Long, end: Long) {
        val e = end.coerceIn(min(minGap, totalFrames), totalFrames)
        this.end = e
        this.start = start.coerceIn(0, max(0, e - minGap))
        invalidate()
    }

    private fun xOf(frame: Long) = if (totalFrames == 0L) 0f else frame.toFloat() / totalFrames * width
    private fun frameOf(x: Float) = (x / max(1, width) * totalFrames).toLong().coerceIn(0, totalFrames)

    override fun onDraw(canvas: Canvas) {
        val w = width
        val h = height.toFloat()
        val mid = h / 2
        canvas.drawLine(0f, mid, w.toFloat(), mid, centre)
        if (peaks.isNotEmpty()) {
            for (x in 0 until w) {
                val a = (x.toLong() * peaks.size / w).toInt()
                val b = max(a + 1, ((x + 1L) * peaks.size / w).toInt()).coerceAtMost(peaks.size)
                var p = 0f
                for (i in a until b) p = max(p, peaks[i])
                // Show level in decibels (-60..0 dB) so quiet parts are still visible.
                val level = if (p <= 0f) 0f else ((20 * log10(p) + 60) / 60).coerceIn(0f, 1f)
                val half = max(0.5f * density, level * (mid - 4 * density))
                canvas.drawLine(x + 0.5f, mid - half, x + 0.5f, mid + half, wave)
            }
        }
        val xs = xOf(start)
        val xe = xOf(end)
        canvas.drawRect(0f, 0f, xs, h, dim)
        canvas.drawRect(xe, 0f, w.toFloat(), h, dim)
        for (x in floatArrayOf(xs, xe)) {
            canvas.drawLine(x, 0f, x, h, handle)
            canvas.drawCircle(x, 8 * density, 8 * density, handle)
            canvas.drawCircle(x, h - 8 * density, 8 * density, handle)
        }
        if (playhead >= 0) {
            val x = xOf(playhead)
            canvas.drawLine(x, 0f, x, h, head)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (totalFrames == 0L || !isEnabled) return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                val ds = abs(event.x - xOf(start))
                val de = abs(event.x - xOf(end))
                dragging = if (ds <= de) 1 else 2
                parent?.requestDisallowInterceptTouchEvent(true) // don't let the page scroll
                move(event.x)
            }
            MotionEvent.ACTION_MOVE -> move(event.x)
            MotionEvent.ACTION_UP -> {
                dragging = 0
                performClick()
            }
            MotionEvent.ACTION_CANCEL -> dragging = 0
        }
        return true
    }

    override fun performClick(): Boolean = super.performClick()

    private fun move(x: Float) {
        val f = frameOf(x)
        if (dragging == 1) setRange(f, end) else if (dragging == 2) setRange(start, f)
        onChange?.invoke(start, end)
    }
}
