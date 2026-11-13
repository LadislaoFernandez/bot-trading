"""Textos y control de "ya avisado" de las notificaciones de operaciones (lo usan el servidor, que manda los avisos
push, y la app de Android, que avisa ella misma mientras está abierta). Los ids ya avisados se guardan en un archivo;
la primera vez solo marca lo que ya existía, para no mandar avisos viejos."""
import json
import os

MAX_VISTOS = 400
REPO = "LadislaoFernandez/bot-trading"
URL_APK = f"https://github.com/{REPO}/releases/latest/download/BotTrading-Control.apk"


def ultima_version_github(repo=REPO, timeout=10, contexto=None):
    """Versión de la última publicación en GitHub ("1.29"), o None. Mira a dónde redirige /releases/latest: no usa la
    API de GitHub (que limita a 60 consultas por hora), así se puede preguntar seguido."""
    destino = _redirige(f"https://github.com/{repo}/releases/latest", timeout, contexto)
    return destino.rsplit("/tag/", 1)[1].strip("/").lstrip("vV") if destino and "/tag/" in destino else None


def version_apk_github(timeout=10, contexto=None):
    """Versión del APK que ya se puede bajar ("1.31"), o None si la última publicación todavía no tiene el APK (se
    agrega unos minutos después del resto). Mira a dónde redirige el link fijo de descarga."""
    destino = _redirige(URL_APK, timeout, contexto)  # GitHub redirige a la última versión aunque no tenga el APK
    if not destino or "/download/" not in destino:
        return None
    if not _redirige(destino, timeout, contexto):  # 404: el APK de esa versión todavía no se subió
        return None
    return destino.split("/download/", 1)[1].split("/", 1)[0].lstrip("vV") or None


def _redirige(url, timeout=10, contexto=None):
    """A dónde redirige la URL (sin seguirla), o None si no existe (404)."""
    import ssl
    import urllib.error
    import urllib.request

    class _SinSeguir(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    abrir = urllib.request.build_opener(_SinSeguir, urllib.request.HTTPSHandler(
        context=contexto or ssl.create_default_context()))
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "bot-trading"})
    try:
        with abrir.open(req, timeout=timeout) as r:
            return r.headers.get("Location", "") or r.geturl()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code not in (301, 302, 303, 307, 308):
            raise
        return e.headers.get("Location", "")


def _num(v, d=2, signo=False):
    if v is None:
        return "—"
    s = f"{abs(v):,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("+" if signo and v > 0 else "-" if v < 0 else "") + s


def _precio(v):
    if v is None:
        return "—"
    return _num(v, 2 if abs(v) >= 100 else 4)


def leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def escribir_json(ruta, datos):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f)
    os.replace(tmp, ruta)


def nuevos(eventos, ruta_vistos):
    """Devuelve los eventos que no se avisaron todavía (del más viejo al más nuevo) y los marca como vistos."""
    estado = leer_json(ruta_vistos, None)
    ids = [e["id"] for e in eventos]
    if not isinstance(estado, dict) or "vistos" not in estado:
        escribir_json(ruta_vistos, dict(estado if isinstance(estado, dict) else {}, vistos=ids[:MAX_VISTOS]))
        return []
    vistos = set(estado["vistos"])
    nuevos_ = [e for e in eventos if e["id"] not in vistos]
    if nuevos_:
        lista = ids + [i for i in estado["vistos"] if i not in set(ids)]
        escribir_json(ruta_vistos, dict(estado, vistos=lista[:MAX_VISTOS]))
    return list(reversed(nuevos_))


def texto(e, modo=""):
    """(título, texto) de la notificación de un evento."""
    lado = "compra" if e.get("lado") == "long" else "venta"
    quien = f"{e.get('activo', '')} · {e.get('estrategia', '')}"
    sufijo = f" ({modo})" if modo else ""
    if e.get("tipo") == "abre":
        partes = [f"A {_precio(e.get('precio'))}"]
        if e.get("stop") is not None:
            partes.append(f"stop {_precio(e['stop'])}")
        if e.get("tamano") is not None:
            partes.append(f"{_num(e['tamano'])} USDT")
        return f"Abrió {lado} en {quien}{sufijo}", " · ".join(partes)
    pnl = e.get("pnl")
    signo = "Ganó" if (pnl or 0) > 0 else "Perdió" if (pnl or 0) < 0 else "Resultado"
    cuerpo = f"Salida a {_precio(e.get('precio'))}"
    if e.get("motivo"):
        cuerpo += f" · {e['motivo']}"
    return f"Cerró {lado} en {quien}: {_num(pnl, 2, True)} USDT{sufijo}", f"{signo} {_num(abs(pnl or 0))} USDT. {cuerpo}"


def version_tupla(v):
    out = []
    for x in str(v or "").strip().lstrip("vV").split("."):
        num = "".join(c for c in x if c.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out + [0] * (3 - len(out)))


def version_nueva(version_servidor, version_app):
    """True si el servidor ya tiene una versión más nueva que la app instalada (cada versión trae su APK)."""
    return bool(version_servidor and version_app) and version_tupla(version_servidor) > version_tupla(version_app)
