"""Avisos para mostrar en la aplicación (estrategias que empeoran o se recuperan, candidatas nuevas del laboratorio).

Se guardan en alertas.json (en la carpeta del bot). Cada aviso tiene un id: si se vuelve a agregar el mismo, no se repite.
"""
import json
import os
import threading
import time

ARCHIVO = "alertas.json"
_lock = threading.Lock()


def _leer():
    try:
        with open(ARCHIVO, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _escribir(lista):
    tmp = ARCHIVO + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lista[-200:], f, ensure_ascii=False, indent=1)
    os.replace(tmp, ARCHIVO)


def agregar(id_, tipo, titulo, texto, datos=None):
    """tipo: 'empeora', 'recupera', 'candidata' o 'info'. Devuelve True si el aviso es nuevo."""
    with _lock:
        lista = _leer()
        if any(a["id"] == id_ for a in lista):
            return False
        lista.append(dict(id=id_, tipo=tipo, titulo=titulo, texto=texto, datos=datos or {}, hora=time.time(), leida=False))
        _escribir(lista)
        return True


def listar(solo_sin_leer=False):
    lista = sorted(_leer(), key=lambda a: a.get("hora", 0), reverse=True)
    return [a for a in lista if not a.get("leida")] if solo_sin_leer else lista


def marcar_leidas(ids=None):
    with _lock:
        lista = _leer()
        for a in lista:
            if ids is None or a["id"] in ids:
                a["leida"] = True
        _escribir(lista)
