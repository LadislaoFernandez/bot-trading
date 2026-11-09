[app]
title = Bot de trading
package.name = botcontrol
package.domain = io.github.ladislaofernandez
source.dir = .
source.include_exts = py,png,json
version = 1.0
requirements = python3,kivy==2.3.0
orientation = portrait
# servicio que avisa aperturas y cierres aunque la app esté cerrada (ver servicio_avisos.py)
services = Avisos:servicio_avisos.py:foreground:sticky
fullscreen = 0
icon.filename = %(source.dir)s/icono.png
presplash.filename = %(source.dir)s/icono.png
android.presplash_color = #0f1115
android.permissions = INTERNET, FOREGROUND_SERVICE, POST_NOTIFICATIONS
# 33 y no 34: con 34 Android 14 exige declarar el tipo de servicio en primer plano, y esta versión de
# python-for-android no lo permite. Para una app que se instala con el APK (no desde Play) no cambia nada.
android.api = 33
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.enable_androidx = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 0
