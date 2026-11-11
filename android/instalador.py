"""Actualización de la app desde la propia app (Android), sin bajar el archivo a mano.

1. Baja el APK nuevo de GitHub a la carpeta privada de la app (con barra de avance).
2. Lo instala con PackageInstaller, el instalador oficial de Android.
   - La primera vez (la app la instaló el navegador), Android pide una sola confirmación, y quizá permitir que esta
     app instale actualizaciones.
   - Desde la segunda, la app ya es "dueña" de su instalación y en Android 12 o más nuevo se actualiza sola, sin
     preguntar (USER_ACTION_NOT_REQUIRED).
3. Android cierra la app para reemplazarla; los datos y el código de conexión se conservan.

El resultado de la instalación vuelve como un Intent a la misma actividad (launchMode singleTask): al_intent().
"""
import os
import ssl
import urllib.request

from jnius import autoclass, cast

ACCION = "io.github.ladislaofernandez.botcontrol.INSTALAR"
PythonActivity = autoclass("org.kivy.android.PythonActivity")
Build = autoclass("android.os.Build$VERSION")
Intent = autoclass("android.content.Intent")

ESTADO_PIDE_CONFIRMAR = -1  # PackageInstaller.STATUS_PENDING_USER_ACTION
ESTADO_OK = 0  # PackageInstaller.STATUS_SUCCESS


def _act():
    return PythonActivity.mActivity


def bajar(url, destino, progreso=None):
    """Baja el APK; progreso(fracción) durante la bajada. Verifica el HTTPS con los certificados de certifi."""
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    tmp = destino + ".parcial"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "bot-trading-android"}),
                                timeout=60, context=ctx) as r, open(tmp, "wb") as f:
        total, hecho = int(r.headers.get("Content-Length") or 0), 0
        while True:
            b = r.read(256 * 1024)
            if not b:
                break
            f.write(b); hecho += len(b)
            if progreso and total:
                progreso(hecho / total)
    if total and hecho != total:
        raise OSError(f"la bajada se cortó ({hecho} de {total} bytes)")
    os.replace(tmp, destino)
    return destino


def instalar(ruta):
    """Abre una sesión de PackageInstaller con el APK y la confirma. El resultado llega por al_intent()."""
    act = _act()
    pi = act.getPackageManager().getPackageInstaller()
    SP = autoclass("android.content.pm.PackageInstaller$SessionParams")
    params = SP(SP.MODE_FULL_INSTALL)
    params.setAppPackageName(act.getPackageName())
    if Build.SDK_INT >= 31:
        params.setRequireUserAction(SP.USER_ACTION_NOT_REQUIRED)  # sin preguntar, si Android lo permite
    sid = pi.createSession(params)
    sesion = pi.openSession(sid)
    try:
        tam = os.path.getsize(ruta)
        out = sesion.openWrite("bot-trading.apk", 0, tam)
        with open(ruta, "rb") as f:
            while True:
                b = f.read(256 * 1024)
                if not b:
                    break
                out.write(b, 0, len(b))
        sesion.fsync(out)
        out.close()
        it = Intent(act, PythonActivity)
        it.setAction(ACCION)
        it.addFlags(0x20000000)  # SINGLE_TOP: vuelve a esta misma pantalla, no abre otra
        flags = 0x08000000 | (0x02000000 if Build.SDK_INT >= 31 else 0)  # UPDATE_CURRENT | MUTABLE
        pend = autoclass("android.app.PendingIntent").getActivity(act, 4321, it, flags)
        sesion.commit(pend.getIntentSender())
    finally:
        sesion.close()


def al_intent(intent, avisar):
    """Resultado de PackageInstaller. avisar(texto) para contarle al usuario si algo falló."""
    if intent is None or intent.getAction() != ACCION:
        return
    estado = intent.getIntExtra("android.content.pm.extra.STATUS", -999)
    if estado == ESTADO_PIDE_CONFIRMAR:  # Android quiere que la persona confirme (primera vez)
        confirmar = cast("android.content.Intent", intent.getParcelableExtra("android.intent.extra.INTENT"))
        confirmar.addFlags(0x10000000)  # NEW_TASK
        _act().startActivity(confirmar)
    elif estado != ESTADO_OK:
        msj = intent.getStringExtra("android.content.pm.extra.STATUS_MESSAGE") or f"estado {estado}"
        avisar(f"No se pudo instalar la versión nueva: {msj}")


def escuchar(avisar):
    from android import activity
    activity.bind(on_new_intent=lambda intent: al_intent(intent, avisar))
