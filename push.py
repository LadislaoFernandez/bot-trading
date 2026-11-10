"""Notificaciones push al celular con Firebase Cloud Messaging (FCM), como Instagram o WhatsApp.

El servidor le manda cada aviso a Google y Google lo entrega en el celular aunque la app esté cerrada y la pantalla
apagada, sin que la app tenga que quedar corriendo. Hace falta:
- firebase-servidor.json en la carpeta del bot: la clave de la "cuenta de servicio" del proyecto de Firebase (secreta).
- que la app de Android se registre (manda su token con la acción push_registrar).
Sin la clave, el resto del bot funciona igual y simplemente no se mandan avisos.
"""
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ARCH_CLAVE = "firebase-servidor.json"
ARCH_TOKENS = "push_tokens.json"
ARCH_VISTOS = "push_vistos.json"
CANAL = "operaciones"  # canal de notificaciones que crea la app de Android
RELAY_POR_HORA = 120  # avisos por hora que acepta el intermediario de cada servidor
_lock = threading.Lock()
_fb_relay = None


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=")


def _leer(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def _escribir(ruta, datos):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, ruta)


def configurado():
    return os.path.exists(ARCH_CLAVE)


# ---------- dispositivos registrados
def tokens():
    return _leer(ARCH_TOKENS, {})


def registrar(token, version=None):
    if not token or len(token) > 4096:
        raise ValueError("Token inválido.")
    with _lock:
        tk = tokens()
        d = tk.get(token, {"alta": time.time()})
        d["version"] = version
        d["visto"] = time.time()
        tk[token] = d
        # un celular reinstalado o con token nuevo deja tokens viejos: guarda los últimos 10
        tk = dict(sorted(tk.items(), key=lambda kv: kv[1].get("visto", 0), reverse=True)[:10])
        _escribir(ARCH_TOKENS, tk)


def quitar(token):
    with _lock:
        tk = tokens()
        if tk.pop(token, None) is not None:
            _escribir(ARCH_TOKENS, tk)


# ---------- envío
class Firebase:
    def __init__(self, ruta=ARCH_CLAVE):
        try:
            os.chmod(ruta, 0o600)
        except OSError:
            pass
        with open(ruta, encoding="utf-8") as f:
            self.cred = json.load(f)
        self.proyecto = self.cred["project_id"]
        self._token, self._vence = None, 0

    def _acceso(self):
        """Token de acceso OAuth2 (dura una hora) firmando un JWT con la clave de la cuenta de servicio."""
        if self._token and time.time() < self._vence - 120:
            return self._token
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        uri = self.cred.get("token_uri") or "https://oauth2.googleapis.com/token"
        ahora = int(time.time())
        cab = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        cuerpo = _b64(json.dumps({"iss": self.cred["client_email"], "aud": uri, "iat": ahora, "exp": ahora + 3600,
                                  "scope": "https://www.googleapis.com/auth/firebase.messaging"}).encode())
        clave = serialization.load_pem_private_key(self.cred["private_key"].encode(), None)
        firma = _b64(clave.sign(cab + b"." + cuerpo, padding.PKCS1v15(), hashes.SHA256()))
        datos = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                        "assertion": (cab + b"." + cuerpo + b"." + firma).decode()}).encode()
        r = json.loads(urllib.request.urlopen(urllib.request.Request(uri, data=datos), timeout=20).read())
        self._token, self._vence = r["access_token"], time.time() + int(r.get("expires_in", 3600))
        return self._token

    def enviar(self, token, titulo, cuerpo, etiqueta=None):
        """Manda una notificación. Devuelve "ok", "invalido" (el token ya no sirve) o el error."""
        msg = {"message": {"token": token,
                           "notification": {"title": titulo, "body": cuerpo},
                           "android": {"priority": "high",
                                       "notification": {"channel_id": CANAL, "tag": etiqueta or None,
                                                        "default_sound": True}}}}
        if not etiqueta:
            msg["message"]["android"]["notification"].pop("tag")
        req = urllib.request.Request(
            f"https://fcm.googleapis.com/v1/projects/{self.proyecto}/messages:send",
            data=json.dumps(msg).encode(), headers={"Authorization": "Bearer " + self._acceso(),
                                                    "Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=20).read()
            return "ok"
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            if e.code == 404 or "UNREGISTERED" in txt or ("INVALID_ARGUMENT" in txt and "token" in txt.lower()):
                return "invalido"
            return f"HTTP {e.code}: {txt[:200]}"


class Relay:
    """Manda los avisos por el servidor del dueño del repositorio (relay.py), que sí tiene la clave de Firebase."""

    def __init__(self, info):
        self.url, self.huella = info["url"].rstrip("/"), info["huella"].lower()

    def enviar(self, token, titulo, cuerpo, etiqueta=None):
        import hashlib
        import http.client
        import ssl
        u = urllib.parse.urlparse(self.url)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # se verifica por huella, como las apps
        con = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=20, context=ctx)
        try:
            con.connect()
            if hashlib.sha256(con.sock.getpeercert(binary_form=True)).hexdigest() != self.huella:
                return "el intermediario no tiene el certificado esperado"
            cuerpo_json = json.dumps({"token": token, "titulo": titulo, "cuerpo": cuerpo, "etiqueta": etiqueta})
            con.request("POST", "/api/relay", body=cuerpo_json, headers={"Content-Type": "application/json"})
            r = con.getresponse()
            d = json.loads(r.read() or b"{}")
            return d.get("resultado") if r.status == 200 else f"intermediario HTTP {r.status}: {d.get('error')}"
        finally:
            con.close()


def relay_disponible():
    if os.environ.get("BOT_SIN_RELAY"):  # pruebas: no tocar el servidor del dueño
        return False
    try:
        import relay
        info = relay.RELAY
    except ImportError:
        return False
    if not info or not info.get("url") or not info.get("huella"):
        return False
    try:  # el propio servidor del dueño no se manda avisos a sí mismo
        with open("servidor_config.json", encoding="utf-8") as f:
            ip = json.load(f).get("ip")
        return not (ip and f"//{ip}:" in info["url"])
    except (OSError, ValueError):
        return True


def emisor():
    """Con quién mandar los avisos: la clave propia de Firebase, el intermediario, o nadie."""
    if configurado():
        return Firebase()
    if relay_disponible():
        import relay
        return Relay(relay.RELAY)
    return None


def relay_enviar(d):
    """Lado del dueño: reenvía a Google un aviso que pidió otro servidor."""
    global _fb_relay
    if not configurado():
        raise ValueError("Este servidor no tiene clave de Firebase.")
    tk, ti, cu = d.get("token"), d.get("titulo"), d.get("cuerpo")
    if not all(isinstance(x, str) for x in (tk, ti, cu)) or not (20 < len(tk) < 4096) or len(ti) > 150 or len(cu) > 500:
        raise ValueError("Aviso inválido.")
    et = d.get("etiqueta")
    et = et[:60] if isinstance(et, str) else None
    _fb_relay = _fb_relay or Firebase()
    return _fb_relay.enviar(tk, ti, cu, et)


def enviar_a_todos(fb, titulo, cuerpo, etiqueta=None):
    """Manda a todos los celulares registrados; borra los tokens que ya no sirven. Devuelve (enviados, errores)."""
    ok, errores = 0, []
    for tk in list(tokens()):
        r = fb.enviar(tk, titulo, cuerpo, etiqueta)
        if r == "ok":
            ok += 1
        elif r == "invalido":
            quitar(tk)
        else:
            errores.append(r)
    return ok, errores


def ciclo(fb, eventos, nombre_modo, version_servidor, log=print):
    """Una vuelta: avisa las aperturas y cierres nuevos y, una vez por versión, que hay una app nueva."""
    import avisos as AV
    n = 0
    if tokens():
        for e in AV.nuevos(eventos, ARCH_VISTOS):
            titulo, cuerpo = AV.texto(e, nombre_modo)
            ok, err = enviar_a_todos(fb, titulo, cuerpo, etiqueta=e["id"][:60])
            n += ok
            for x in err:
                log(f"Aviso al celular no enviado: {x}")
    else:
        AV.nuevos(eventos, ARCH_VISTOS)  # sin celulares registrados solo marca lo visto (no acumula avisos viejos)
    with _lock:
        tk = tokens()
    for token, d in tk.items():
        if AV.version_nueva(version_servidor, d.get("version")) and d.get("avisada") != version_servidor:
            r = fb.enviar(token, f"Hay una versión nueva de la app ({version_servidor})",
                          "Abrí la app y tocá \"Bajar la versión nueva\". Tus datos y el código se conservan.",
                          etiqueta="version")
            if r == "invalido":
                quitar(token)
            elif r == "ok":
                with _lock:
                    t2 = tokens()
                    if token in t2:
                        t2[token]["avisada"] = version_servidor
                        _escribir(ARCH_TOKENS, t2)
    return n
