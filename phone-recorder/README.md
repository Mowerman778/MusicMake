# MusicMake Recorder (Android)

A small Android app that records whatever your phone is playing and saves it as an MP3.
It does not use the microphone's sound: it captures the phone's own audio output.

- Start recording, play something in another app, come back (or use the notification) and stop.
- **Trim** before saving: the trim screen opens with the dead spots at the start and end already
  marked (anything quieter than about -50 dB). Drag the handles on the waveform, nudge them by
  0.1 s, and preview the start or the ending. Short fades at the cuts stop them clicking.
- Save as MP3 at 128, 192 or 320 kbps. Audio is 48 kHz stereo, encoded on the phone.
- Files go to **Music/MusicMake Recorder** on the phone, so music players and file apps see them.
- Until you save it, the recording waits in the app (about 11 MB a minute), even if you close it.
- A level meter shows whether sound is being captured.

## Requirements and limits

- Android 10 or newer. iPhones don't allow an app to record other apps' audio, so there is no iOS version.
- Android asks two things: the microphone permission (Android files playback capture under it)
  and "start recording or casting?" each time. Pick the entire screen, or the one app to record.
- Apps can opt out of being recorded. Many streaming and video apps do, and calls are never
  captured. Those give a silent file; the app tells you when a recording came out silent.
- Only record things you have the right to keep.

## Get the APK

On your phone, open this link and install the file it downloads:

https://github.com/Mowerman778/MusicMake/releases/download/recorder-latest/MusicMake-Recorder.apk

Allow installing from your browser when Android asks. Every push that touches `phone-recorder/`
rebuilds the APK on GitHub Actions and replaces that file, so the link always gets the newest build.

The APK is signed with a debug key, which is fine for your own phone. Builds reuse one key kept
in the Actions cache, so a new APK installs over the old one. GitHub drops a cache that goes
unused for 7 days; after that, the next build has a new key and you uninstall the old app once
first (your saved MP3s stay in Music). Because the repository is public, anyone with the link
can download the APK.

## Build it yourself

Open this folder in Android Studio and press Run, or from a terminal with the Android SDK installed:

```sh
cd phone-recorder
./gradlew testReleaseUnitTest      # unit tests for trimming and MP3 encoding
./gradlew assembleRelease          # app/build/outputs/apk/release/app-release.apk
adb install app/build/outputs/apk/release/app-release.apk
```

## How it works

| File | What it does |
|---|---|
| `MainActivity.kt` | The screen: permissions, the capture prompt, timer, meter, play and share |
| `RecordService.kt` | Foreground service: `AudioPlaybackCaptureConfiguration` → `AudioRecord` → raw PCM in app storage |
| `TrimActivity.kt`, `WaveformView.kt`, `Preview.kt` | The trim screen: waveform with handles, preview playback, save |
| `Trim.kt` | Waveform overview, silence detection and trimmed export (unit-tested in `app/src/test`) |
| `Pending.kt`, `Library.kt` | The recording waiting to be saved, and saving MP3s to MediaStore |
| `Mp3Encoder.java` | MP3 encoding with [jump3r](https://github.com/Sciss/jump3r), a pure-Java port of LAME (LGPL-2.1+) |
| `RecorderState.kt` | Shared state the service updates and the screen shows |

It has no network permission and sends nothing anywhere.
