[app]
title = Bot de trading
package.name = botcontrol
package.domain = io.github.ladislaofernandez
source.dir = .
source.include_exts = py,png,json
version = 1.0
requirements = python3,kivy==2.3.0
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icono.png
presplash.filename = %(source.dir)s/icono.png
android.presplash_color = #0f1115
android.permissions = INTERNET
android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.enable_androidx = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 0
