"""Notificaciones en Android: canal, avisos locales y token de Firebase (push).

Los avisos de operaciones llegan por Firebase Cloud Messaging: el servidor los manda a Google y Google los muestra
aunque la app esté cerrada (como Instagram). Mientras la app está abierta, Android no muestra esos avisos solo, así que
la app los muestra ella misma (notificar()).
"""
import zlib

from jnius import PythonJavaClass, autoclass, cast, java_method

CANAL = "operaciones"  # el mismo que usa el servidor al mandar el push

PythonActivity = autoclass("org.kivy.android.PythonActivity")
Context = autoclass("android.content.Context")
Build = autoclass("android.os.Build$VERSION")
NotificationManager = autoclass("android.app.NotificationManager")
JString = autoclass("java.lang.String")


def _act():
    return PythonActivity.mActivity


def _nm():
    return cast(NotificationManager, _act().getSystemService(Context.NOTIFICATION_SERVICE))


def crear_canal():
    if Build.SDK_INT >= 26:
        Canal = autoclass("android.app.NotificationChannel")
        ch = Canal(CANAL, JString("Operaciones del bot"), NotificationManager.IMPORTANCE_HIGH)
        ch.setDescription(JString("Cuando el bot abre o cierra una operación"))
        _nm().createNotificationChannel(ch)


def pedir_permiso():
    """Android 13 o más: la primera vez pide permiso para mostrar notificaciones."""
    try:
        from android.permissions import Permission, request_permissions
        if hasattr(Permission, "POST_NOTIFICATIONS"):
            request_permissions([Permission.POST_NOTIFICATIONS])
    except Exception:
        pass


def notificar(id_, titulo, cuerpo):
    act = _act()
    Builder = autoclass("android.app.Notification$Builder")
    BigText = autoclass("android.app.Notification$BigTextStyle")
    PendingIntent = autoclass("android.app.PendingIntent")
    b = Builder(act, CANAL) if Build.SDK_INT >= 26 else Builder(act)
    b.setSmallIcon(act.getApplicationInfo().icon)
    b.setContentTitle(JString(titulo))
    b.setContentText(JString(cuerpo))
    b.setStyle(BigText().bigText(JString(cuerpo)))
    b.setAutoCancel(True)
    intent = act.getPackageManager().getLaunchIntentForPackage(act.getPackageName())
    b.setContentIntent(PendingIntent.getActivity(act, 0, intent, 0x04000000 | 0x08000000))  # IMMUTABLE | UPDATE
    _nm().notify(zlib.crc32(id_.encode("utf-8")) & 0x7FFFFFFF, b.build())


class _AlTerminar(PythonJavaClass):
    __javainterfaces__ = ["com/google/android/gms/tasks/OnCompleteListener"]
    __javacontext__ = "app"

    def __init__(self, cb):
        super().__init__()
        self.cb = cb

    @java_method("(Lcom/google/android/gms/tasks/Task;)V")
    def onComplete(self, task):
        try:
            if task.isSuccessful():
                self.cb(str(task.getResult()), None)
            else:
                self.cb(None, str(task.getException()))
        except Exception as e:
            self.cb(None, f"{type(e).__name__}: {e}")


_vivos = []  # que Python no borre el listener antes de que Java lo llame


def pedir_token(cb):
    """Pide el token de Firebase de este celular; cb(token, error) se llama cuando llega."""
    FirebaseMessaging = autoclass("com.google.firebase.messaging.FirebaseMessaging")
    oyente = _AlTerminar(cb)
    _vivos.append(oyente)
    FirebaseMessaging.getInstance().getToken().addOnCompleteListener(oyente)
