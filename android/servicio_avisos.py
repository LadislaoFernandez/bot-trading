"""Servicio de Android que avisa con una notificación cuando el bot abre o cierra una operación.

Corre aparte de la pantalla de la app (sigue aunque la cierres) y muestra una notificación fija "Avisos de operaciones",
que es lo que Android exige para que no lo mate. Cada minuto le pregunta al servidor si hubo aperturas o cierres nuevos.
La app lo arranca al abrirse y lo apaga si desactivás los avisos en Control.
"""
import json
import os
import time
import traceback
import zlib

from jnius import autoclass, cast

import avisos as AV
import cliente_api as C

PythonService = autoclass("org.kivy.android.PythonService")
Context = autoclass("android.content.Context")
Build = autoclass("android.os.Build$VERSION")
NotificationManager = autoclass("android.app.NotificationManager")
Builder = autoclass("android.app.Notification$Builder")
BigText = autoclass("android.app.Notification$BigTextStyle")
PendingIntent = autoclass("android.app.PendingIntent")
Intent = autoclass("android.content.Intent")
Uri = autoclass("android.net.Uri")
JString = autoclass("java.lang.String")

CANAL = "operaciones"
CADA = 60  # segundos entre consultas al servidor

svc = PythonService.mService
args = json.loads(os.environ.get("PYTHON_SERVICE_ARGUMENT") or "{}")
CARPETA = args.get("carpeta") or os.environ.get("ANDROID_PRIVATE") or "."
ARCH_CODIGO = os.path.join(CARPETA, "codigo.json")
ARCH_VISTOS = os.path.join(CARPETA, "avisos_vistos.json")
ARCH_AJUSTES = os.path.join(CARPETA, "avisos_ajustes.json")
ARCH_ERROR = os.path.join(CARPETA, "avisos_error.log")

nm = cast(NotificationManager, svc.getSystemService(Context.NOTIFICATION_SERVICE))
if Build.SDK_INT >= 26:
    Canal = autoclass("android.app.NotificationChannel")
    ch = Canal(CANAL, JString("Operaciones del bot"), NotificationManager.IMPORTANCE_HIGH)
    ch.setDescription(JString("Cuando el bot abre o cierra una operación"))
    nm.createNotificationChannel(ch)


def _pendiente(intent, codigo=0):
    flags = 0x04000000 if Build.SDK_INT >= 23 else 0  # FLAG_IMMUTABLE
    return PendingIntent.getActivity(svc, codigo, intent, flags | 0x08000000)  # | FLAG_UPDATE_CURRENT


def _abrir_app():
    return _pendiente(svc.getPackageManager().getLaunchIntentForPackage(svc.getPackageName()))


def version_app():
    try:
        return svc.getPackageManager().getPackageInfo(svc.getPackageName(), 0).versionName
    except Exception:
        return None


def notificar_version(v):
    """Aviso de app nueva: al tocarlo baja el APK de la última versión (Android pide confirmar la instalación)."""
    i = Intent(Intent.ACTION_VIEW, Uri.parse(AV.URL_APK))
    notificar(f"version|{v}", f"Hay una versión nueva de la app ({v})",
              "Tocá acá para bajarla. Cuando termine la descarga, abrila y tocá Actualizar. Tus datos y el código de "
              "conexión se conservan.", intent=_pendiente(i, 1))


def notificar(id_, titulo, cuerpo, intent=None):
    b = Builder(svc, CANAL) if Build.SDK_INT >= 26 else Builder(svc)
    b.setSmallIcon(svc.getApplicationInfo().icon)
    b.setContentTitle(JString(titulo))
    b.setContentText(JString(cuerpo))
    b.setStyle(BigText().bigText(JString(cuerpo)))
    b.setAutoCancel(True)
    b.setContentIntent(intent or _abrir_app())
    if Build.SDK_INT < 26:
        b.setPriority(1)  # PRIORITY_HIGH
    nm.notify(zlib.crc32(id_.encode("utf-8")) & 0x7FFFFFFF, b.build())


def _anotar_error(texto):
    try:
        with open(ARCH_ERROR, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + texto + "\n")
        if os.path.getsize(ARCH_ERROR) > 100_000:
            os.replace(ARCH_ERROR, ARCH_ERROR + ".1")
    except OSError:
        pass


def _mantener_despierto():
    """Sin esto, con la pantalla apagada Android duerme el procesador (Doze) y el servicio deja de consultar al servidor
    hasta que se abre la app. Funciona del todo si la app está excluida del ahorro de batería (la app lo pide)."""
    try:
        PowerManager = autoclass("android.os.PowerManager")
        pm = cast(PowerManager, svc.getSystemService(Context.POWER_SERVICE))
        wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, JString("BotTrading:avisos"))
        wl.setReferenceCounted(False)
        wl.acquire()
        return wl
    except Exception:
        _anotar_error("wakelock: " + traceback.format_exc())
        return None


def main():
    if hasattr(svc, "setAutoRestartService"):
        svc.setAutoRestartService(True)
    wl = _mantener_despierto()
    cliente, codigo = None, None
    while True:
        if not AV.leer_json(ARCH_AJUSTES, {}).get("activo", True):
            if hasattr(svc, "setAutoRestartService"):
                svc.setAutoRestartService(False)
            if wl is not None and wl.isHeld():
                wl.release()
            svc.stopSelf()
            return
        try:
            cod = (AV.leer_json(ARCH_CODIGO, {}) or {}).get("codigo")
            if cod and cod != codigo:
                cliente, codigo = C.Cliente(cod), cod
            if cliente:
                AV.ciclo(cliente, ARCH_VISTOS, notificar, version_app(), notificar_version)
        except (C.ErrorConexion, C.ErrorServidor) as e:
            _anotar_error(str(e))  # sin internet o servidor caído: se reintenta en la próxima vuelta
        except Exception:
            _anotar_error(traceback.format_exc())
        time.sleep(CADA)


main()
