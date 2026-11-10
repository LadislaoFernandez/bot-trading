[app]
title = Bot de trading
package.name = botcontrol
package.domain = io.github.ladislaofernandez
source.dir = .
source.include_exts = py,png,json
version = 1.0
requirements = python3,kivy==2.3.0,certifi
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icono.png
presplash.filename = %(source.dir)s/icono.png
android.presplash_color = #0f1115
android.permissions = INTERNET, POST_NOTIFICATIONS
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
# release firmado con la llave fija (ver .github/workflows/android.yml); APK y no AAB porque se instala a mano
android.release_artifact = apk
android.enable_androidx = True
# avisos push con Firebase Cloud Messaging (como Instagram): la configuración del proyecto va como recursos de Android
# (res_firebase/values/firebase.xml lo arma el workflow desde google-services.json)
android.gradle_dependencies = com.google.firebase:firebase-messaging:23.4.1
android.add_resources = res_firebase/values/firebase.xml:values/firebase.xml
android.meta_data = com.google.firebase.messaging.default_notification_channel_id=operaciones
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 0
