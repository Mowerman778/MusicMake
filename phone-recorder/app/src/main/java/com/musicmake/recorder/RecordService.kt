package com.musicmake.recorder

import android.Manifest
import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.MediaStore
import java.io.BufferedOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs
import kotlin.math.max

/**
 * Foreground service that records what the phone is playing (Android's
 * AudioPlaybackCapture) and encodes it straight to an MP3 in Music/MusicMake Recorder.
 */
class RecordService : Service() {

    private var projection: MediaProjection? = null
    private var worker: Thread? = null
    @Volatile private var stopRequested = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> start(intent)
            ACTION_STOP -> stopRequested = true
        }
        return START_NOT_STICKY
    }

    private fun start(intent: Intent) {
        if (worker != null) return
        val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, Activity.RESULT_CANCELED)
        val data: Intent? = if (Build.VERSION.SDK_INT >= 33) {
            intent.getParcelableExtra(EXTRA_DATA, Intent::class.java)
        } else {
            @Suppress("DEPRECATION") intent.getParcelableExtra(EXTRA_DATA)
        }
        val kbps = intent.getIntExtra(EXTRA_KBPS, 192)
        if (resultCode != Activity.RESULT_OK || data == null) {
            RecorderState.failed("Recording was not allowed.")
            stopSelf()
            return
        }

        // Android requires the foreground service to be running before the projection is used.
        var types = ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
            types = types or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        }
        startForeground(NOTIFICATION_ID, notification(), types)

        val manager = getSystemService(MediaProjectionManager::class.java)!!
        val projection = try {
            manager.getMediaProjection(resultCode, data)
        } catch (e: Exception) {
            null
        }
        if (projection == null) {
            RecorderState.failed("Could not start recording. Please try again.")
            shutDown()
            return
        }
        this.projection = projection
        projection.registerCallback(object : MediaProjection.Callback() {
            // The user can end sharing from the system UI; finish the file when they do.
            override fun onStop() { stopRequested = true }
        }, Handler(Looper.getMainLooper()))

        stopRequested = false
        worker = Thread({ record(projection, kbps) }, "recorder").also { it.start() }
    }

    private fun record(projection: MediaProjection, kbps: Int) {
        val config = AudioPlaybackCaptureConfiguration.Builder(projection)
            .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
            .addMatchingUsage(AudioAttributes.USAGE_GAME)
            .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
            .build()
        val format = AudioFormat.Builder()
            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
            .setSampleRate(SAMPLE_RATE)
            .setChannelMask(AudioFormat.CHANNEL_IN_STEREO)
            .build()
        val minBuffer = AudioRecord.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_STEREO, AudioFormat.ENCODING_PCM_16BIT
        )
        // About two seconds of slack so a slow encode never drops audio.
        val bufferBytes = max(minBuffer, SAMPLE_RATE * CHANNELS * 2 * 2)

        val audio: AudioRecord = try {
            AudioRecord.Builder()
                .setAudioFormat(format)
                .setBufferSizeInBytes(bufferBytes)
                .setAudioPlaybackCaptureConfig(config)
                .build()
        } catch (e: SecurityException) {
            RecorderState.failed("Microphone permission is needed to record phone audio.")
            shutDown(); return
        } catch (e: Exception) {
            RecorderState.failed("Could not open the audio stream: ${e.message}")
            shutDown(); return
        }

        val name = "Recording " +
            SimpleDateFormat("yyyy-MM-dd HH-mm-ss", Locale.US).format(Date()) + ".mp3"
        val uri = createFile(name)
        if (uri == null) {
            audio.release()
            RecorderState.failed("Could not create the MP3 file.")
            shutDown(); return
        }

        var peakEver = 0
        try {
            val stream = contentResolver.openOutputStream(uri) ?: error("cannot open file")
            Mp3Encoder(BufferedOutputStream(stream, 64 * 1024), SAMPLE_RATE, CHANNELS, kbps).use { mp3 ->
                val pcm = ShortArray(SAMPLE_RATE / 10 * CHANNELS) // 100 ms
                audio.startRecording()
                RecorderState.started()
                while (!stopRequested) {
                    val n = audio.read(pcm, 0, pcm.size)
                    if (n < 0) error("audio read failed ($n)")
                    if (n == 0) continue
                    var peak = 0
                    for (i in 0 until n) peak = max(peak, abs(pcm[i].toInt()))
                    peakEver = max(peakEver, peak)
                    RecorderState.level(peak / 32768f)
                    mp3.encode(pcm, n)
                }
                audio.stop()
            }
            publishFile(uri)
            RecorderState.saved(name, uri, silent = peakEver == 0)
        } catch (e: Exception) {
            contentResolver.delete(uri, null, null)
            RecorderState.failed("Recording failed: ${e.message}")
        } finally {
            audio.release()
            shutDown()
        }
    }

    /** A pending entry in Music/MusicMake Recorder; it stays hidden until publishFile. */
    private fun createFile(name: String): Uri? {
        val values = ContentValues().apply {
            put(MediaStore.Audio.Media.DISPLAY_NAME, name)
            put(MediaStore.Audio.Media.MIME_TYPE, "audio/mpeg")
            put(MediaStore.Audio.Media.RELATIVE_PATH, "${Environment.DIRECTORY_MUSIC}/MusicMake Recorder")
            put(MediaStore.Audio.Media.IS_PENDING, 1)
        }
        val collection = MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
        return contentResolver.insert(collection, values)
    }

    private fun publishFile(uri: Uri) {
        val values = ContentValues().apply { put(MediaStore.Audio.Media.IS_PENDING, 0) }
        contentResolver.update(uri, values, null, null)
    }

    private fun shutDown() {
        Handler(Looper.getMainLooper()).post {
            projection?.stop()
            projection = null
            worker = null
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun notification(): Notification {
        val nm = getSystemService(NotificationManager::class.java)!!
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Recording", NotificationManager.IMPORTANCE_LOW)
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
        )
        val stop = PendingIntent.getService(
            this, 1, Intent(this, RecordService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("Recording phone audio")
            .setContentText("Tap Stop to save the MP3.")
            .setContentIntent(open)
            .setOngoing(true)
            .addAction(Notification.Action.Builder(null, "Stop", stop).build())
            .build()
    }

    companion object {
        const val SAMPLE_RATE = 48_000
        const val CHANNELS = 2
        private const val CHANNEL_ID = "recording"
        private const val NOTIFICATION_ID = 1
        private const val ACTION_START = "start"
        private const val ACTION_STOP = "stop"
        private const val EXTRA_RESULT_CODE = "resultCode"
        private const val EXTRA_DATA = "data"
        private const val EXTRA_KBPS = "kbps"

        fun start(context: Context, resultCode: Int, data: Intent, kbps: Int) {
            val intent = Intent(context, RecordService::class.java)
                .setAction(ACTION_START)
                .putExtra(EXTRA_RESULT_CODE, resultCode)
                .putExtra(EXTRA_DATA, data)
                .putExtra(EXTRA_KBPS, kbps)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            context.startService(Intent(context, RecordService::class.java).setAction(ACTION_STOP))
        }
    }
}
