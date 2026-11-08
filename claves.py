"""Guarda las claves de API de Binance.

En Windows van cifradas con la protección de datos de Windows (DPAPI): solo el mismo usuario, en la misma PC, puede
descifrarlas. En el servidor (Linux) van en un archivo que solo puede leer el usuario del bot (permisos 600), dentro de
la máquina virtual que solo administra el dueño. Las claves nunca se mandan por la red ni se muestran completas.
"""
import ctypes
import json
import os

WINDOWS = os.name == "nt"
if WINDOWS:
    import ctypes.wintypes as W

ARCHIVO = {"demo": "claves_demo.dat", "real": "claves_real.dat"}


if WINDOWS:
    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", W.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _proteger(data: bytes) -> bytes:
    if not WINDOWS:
        return data  # en Linux protege el permiso 600 del archivo (ver _escribir)
    entrada, _buf = _blob(data)
    salida = _BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(entrada), "bot-trading", None, None, None, 0,
                                                  ctypes.byref(salida)):
        raise OSError("No se pudieron cifrar las claves")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(salida.pbData)


def _desproteger(data: bytes) -> bytes:
    if not WINDOWS:
        return data
    entrada, _buf = _blob(data)
    salida = _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(entrada), None, None, None, None, 0,
                                                    ctypes.byref(salida)):
        raise OSError("No se pudieron descifrar las claves (¿otro usuario de Windows?)")
    try:
        return ctypes.string_at(salida.pbData, salida.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(salida.pbData)


def guardar(modo, api_key, secret):
    secret = secret.strip() if "PRIVATE KEY" not in secret else secret.strip() + "\n"
    datos = json.dumps({"key": api_key.strip(), "secret": secret}).encode("utf-8")
    import archivos
    tmp = f"{ARCHIVO[modo]}.{os.getpid()}.tmp"
    _escribir(tmp, _proteger(datos))
    archivos.reemplazar(tmp, ARCHIVO[modo])


def _escribir(ruta, datos):
    """Escribe el archivo; en Linux, creado directamente con permisos 600 (solo el usuario del bot lo puede leer)."""
    if WINDOWS:
        with open(ruta, "wb") as f:
            f.write(datos)
        return
    fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(datos)
    os.chmod(ruta, 0o600)


def cargar(modo):
    try:
        with open(ARCHIVO[modo], "rb") as f:
            d = json.loads(_desproteger(f.read()).decode("utf-8"))
        return d["key"], d["secret"]
    except (OSError, ValueError, KeyError):
        return None


def hay(modo):
    return os.path.exists(ARCHIVO[modo])


def borrar(modo):
    try:
        os.remove(ARCHIVO[modo])
    except OSError:
        pass


def enmascarar(api_key):
    return (api_key[:4] + "…" + api_key[-4:]) if api_key and len(api_key) > 10 else "…"


# ------------------------------------------------------------------ claves Ed25519 generadas en esta PC
def generar_ed25519():
    """Genera un par de claves Ed25519. Devuelve (privada_pem, publica_pem). La privada nunca sale de la PC."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                           serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


def guardar_privada_pendiente(modo, priv, pub):
    """Guarda la clave privada cifrada hasta que el usuario cargue la clave de API que le da Binance."""
    datos = json.dumps({"priv": priv, "pub": pub}).encode("utf-8")
    _escribir(f"ed25519_{modo}.dat", _proteger(datos))


def cargar_privada_pendiente(modo):
    try:
        with open(f"ed25519_{modo}.dat", "rb") as f:
            d = json.loads(_desproteger(f.read()).decode("utf-8"))
        return d["priv"], d["pub"]
    except (OSError, ValueError, KeyError):
        return None


def completar_ed25519(modo, api_key):
    """Une la clave de API de Binance con la privada Ed25519 ya guardada."""
    par = cargar_privada_pendiente(modo)
    if not par:
        raise OSError("Primero generá el par de claves Ed25519 en la app")
    guardar(modo, api_key, par[0])
