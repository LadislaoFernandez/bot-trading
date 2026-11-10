"""Textos y control de "ya avisado" de las notificaciones de operaciones (lo usan el servidor, que manda los avisos
push, y la app de Android, que avisa ella misma mientras está abierta). Los ids ya avisados se guardan en un archivo;
la primera vez solo marca lo que ya existía, para no mandar avisos viejos."""
import json
import os

MAX_VISTOS = 400
URL_APK = "https://github.com/LadislaoFernandez/bot-trading/releases/latest/download/BotTrading-Control.apk"


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
