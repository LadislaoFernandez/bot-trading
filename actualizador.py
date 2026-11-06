"""Actualizaciones de la aplicación desde las versiones publicadas en GitHub.

Cada versión publicada (release) en el repositorio trae un archivo actualizacion.zip con el código del bot. Instalar
una actualización:
  1. guarda una copia del código actual en respaldos/<versión>,
  2. reemplaza los archivos del código (nunca toca estado, operaciones, registro, ajustes ni claves),
  3. si cambiaron las dependencias, las instala con pip,
  4. y la aplicación se reinicia sola.
"""
import hashlib
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

import config as K

ASSET = "actualizacion.zip"
# archivos con datos del usuario: una actualización nunca los pisa aunque vinieran en el zip
PROTEGIDOS = {"ajustes.json", "historial_estrategias.json"}
EXT_PROTEGIDAS = (".json", ".jsonl", ".csv", ".log", ".dat", ".txt")


def version_tupla(v):
    v = (v or "").strip().lstrip("vV")
    out = []
    for x in v.split("."):
        num = "".join(c for c in x if c.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out + [0] * (3 - len(out)))


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "BotTrading-updater", "Accept": "application/vnd.github+json"})
    tok = os.environ.get("BOT_TRADING_GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    ctx = ssl.create_default_context()
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def buscar():
    """Devuelve None si no hay nada nuevo, o un diccionario con la versión disponible."""
    if not getattr(K, "REPO", ""):
        raise RuntimeError("repo-no-configurado")
    with _get(f"https://api.github.com/repos/{K.REPO}/releases/latest") as r:
        rel = json.loads(r.read().decode("utf-8"))
    ver = rel.get("tag_name", "")
    asset = next((a for a in rel.get("assets", []) if a.get("name") == ASSET), None)
    if not asset or version_tupla(ver) <= version_tupla(K.VERSION):
        return None
    instalador = next((a["browser_download_url"] for a in rel.get("assets", []) if a.get("name", "").endswith(".exe")), None)
    return dict(version=ver.lstrip("vV"), notas=(rel.get("body") or "").strip(), url=asset["browser_download_url"],
                tamano=asset.get("size"), pagina=rel.get("html_url"), instalador=instalador)


def _python_consola():
    exe = sys.executable
    d, n = os.path.split(exe)
    if n.lower() == "pythonw.exe" and os.path.exists(os.path.join(d, "python.exe")):
        return os.path.join(d, "python.exe")
    return exe


def _hash(p):
    try:
        with open(p, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def instalar(info, progreso=None, carpeta="."):
    """Baja e instala la actualización. Devuelve la lista de archivos reemplazados. La app tiene que reiniciarse."""
    carpeta = os.path.abspath(carpeta)
    aviso = progreso or (lambda f, x: None)
    tmp = tempfile.mkdtemp(prefix="bot_actualizacion_")
    try:
        zp = os.path.join(tmp, ASSET)
        aviso(0.05, "descargando")
        with _get(info["url"], timeout=120) as r, open(zp, "wb") as f:
            total, n = info.get("tamano") or 0, 0
            while True:
                b = r.read(65536)
                if not b:
                    break
                f.write(b); n += len(b)
                if total:
                    aviso(0.05 + 0.6 * n / total, "descargando")
        with zipfile.ZipFile(zp) as z:
            if z.testzip() is not None:
                raise RuntimeError("zip-danado")
            nombres = [x for x in z.namelist() if not x.endswith("/")]
            for x in nombres:  # nada fuera de la carpeta del bot
                if x.startswith(("/", "\\")) or ".." in x.replace("\\", "/").split("/"):
                    raise RuntimeError("zip-invalido")
            dest = os.path.join(tmp, "nuevo")
            z.extractall(dest)
        if not os.path.exists(os.path.join(dest, "app.py")):
            raise RuntimeError("zip-sin-app")
        aviso(0.7, "respaldando")
        req_antes = _hash(os.path.join(carpeta, "requirements.txt"))
        resp = os.path.join(carpeta, "respaldos", K.VERSION)
        os.makedirs(resp, exist_ok=True)
        cambiados = []
        for x in nombres:
            if os.path.basename(x) in PROTEGIDOS or x.lower().endswith(EXT_PROTEGIDAS) and x != "requirements.txt":
                continue
            src, dst = os.path.join(dest, x), os.path.join(carpeta, x)
            if os.path.exists(dst):
                os.makedirs(os.path.dirname(os.path.join(resp, x)), exist_ok=True)
                shutil.copy2(dst, os.path.join(resp, x))
            cambiados.append((src, dst))
        aviso(0.8, "copiando")
        for src, dst in cambiados:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
        if _hash(os.path.join(carpeta, "requirements.txt")) != req_antes:
            aviso(0.85, "dependencias")
            flags = 0x08000000 if os.name == "nt" else 0  # sin ventana de consola
            r = subprocess.run([_python_consola(), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r",
                                os.path.join(carpeta, "requirements.txt")], cwd=carpeta, capture_output=True, text=True,
                               creationflags=flags)
            if r.returncode != 0:
                raise RuntimeError("pip: " + (r.stderr or r.stdout)[-300:])
        aviso(1.0, "listo")
        return [os.path.relpath(d, carpeta) for _, d in cambiados]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
