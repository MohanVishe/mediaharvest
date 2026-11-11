import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// Release signing is read from a properties file kept outside the repository:
// MH_SIGNING=/path/to/keystore.properties (storeFile, storePassword, keyAlias,
// keyPassword). Without it, release builds come out unsigned.
val appVersion = "1.0.0"

val signing: Properties? = System.getenv("MH_SIGNING")?.let { path ->
    Properties().apply { file(path).inputStream().use { load(it) } }
}

android {
    namespace = "io.github.mohanvishe.mediaharvest"
    compileSdk = 37

    defaultConfig {
        applicationId = "io.github.mohanvishe.mediaharvest"
        minSdk = 29
        targetSdk = 36
        versionCode = 1
        versionName = appVersion
    }

    signingConfigs {
        if (signing != null) {
            create("release") {
                storeFile = file(signing.getProperty("storeFile"))
                storePassword = signing.getProperty("storePassword")
                keyAlias = signing.getProperty("keyAlias")
                keyPassword = signing.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("release")
        }
    }

    // One APK per processor type keeps each download small. x86_64 is for
    // emulators and Chromebooks.
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "armeabi-v7a", "x86_64")
            isUniversalApk = false
        }
    }

    // yt-dlp's Python, ffmpeg and QuickJS run as programs from the app's
    // library folder, so Android must unpack them on install.
    packaging {
        jniLibs { useLegacyPackaging = true }
    }

    buildFeatures { compose = true }

    // The app is in English; drops the libraries' other languages.
    androidResources { localeFilters += "en" }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // No dependency report signed for Google Play inside the APK.
    dependenciesInfo {
        includeInApk = false
        includeInBundle = false
    }
}

// APKs come out as MediaHarvest-1.0.0-arm64-v8a-release.apk and so on.
base.archivesName = "MediaHarvest-$appVersion"

dependencies {
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.foundation)
    implementation(libs.compose.material3)
    implementation(libs.activity.compose)
    implementation(libs.youtubedl.library)
    implementation(libs.youtubedl.ffmpeg)
    implementation(libs.kotlinx.coroutines.android)
    testImplementation(libs.junit)
    constraints {
        // The engine asks for Jackson 2.11.1, which has known parser bugs; its
        // updater feeds Jackson replies from the network.
        implementation(libs.jackson.databind)
    }
}
