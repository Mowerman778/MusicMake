plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.musicmake.recorder"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.musicmake.recorder"
        // Recording other apps' audio (AudioPlaybackCapture) needs Android 10.
        minSdk = 29
        targetSdk = 35
        versionCode = 2
        versionName = "1.1"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            // Signed with the debug key so the APK installs without extra setup.
            // It is a personal app; make your own key before sharing it.
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // Pure-Java LAME port (LGPL-2.1+), used for MP3 encoding on the phone.
    implementation("de.sciss:jump3r:1.0.5")
    testImplementation("junit:junit:4.13.2")
}
