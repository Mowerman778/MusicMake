# MusicMake Recorder (Android)

A small Android app that records whatever your phone is playing and saves it as an MP3.
It does not use the microphone's sound: it captures the phone's own audio output.

- Start recording, play something in another app, come back (or use the notification) and stop.
- Files go to **Music/MusicMake Recorder** on the phone, so music players and file apps see them.
- Choose 128, 192 or 320 kbps. Audio is 48 kHz stereo, encoded on the phone.
- A level meter shows whether sound is being captured.

## Requirements and limits

- Android 10 or newer. iPhones don't allow an app to record other apps' audio, so there is no iOS version.
- Android asks two things: the microphone permission (Android files playback capture under it)
  and "start recording or casting?" each time. Pick the entire screen, or the one app to record.
- Apps can opt out of being recorded. Many streaming and video apps do, and calls are never
  captured. Those give a silent file; the app tells you when a recording came out silent.
- Only record things you have the right to keep.

## Get the APK

Every push that touches `phone-recorder/` builds it on GitHub Actions
(workflow "Phone recorder APK"). Open the run, download the `musicmake-recorder-apk` artifact,
unzip it and copy `app-release.apk` to the phone. Open it there and allow installing from
that source when Android asks.

The APK is signed with a debug key, which is fine for your own phone.

## Build it yourself

Open this folder in Android Studio and press Run, or from a terminal with the Android SDK installed:

```sh
cd phone-recorder
./gradlew assembleRelease          # app/build/outputs/apk/release/app-release.apk
adb install app/build/outputs/apk/release/app-release.apk
```

## How it works

| File | What it does |
|---|---|
| `MainActivity.kt` | The screen: permissions, the capture prompt, timer, meter, play and share |
| `RecordService.kt` | Foreground service: `AudioPlaybackCaptureConfiguration` → `AudioRecord` → MP3 in MediaStore |
| `Mp3Encoder.java` | MP3 encoding with [jump3r](https://github.com/Sciss/jump3r), a pure-Java port of LAME (LGPL-2.1+) |
| `RecorderState.kt` | Shared state the service updates and the screen shows |

It has no network permission and sends nothing anywhere.
