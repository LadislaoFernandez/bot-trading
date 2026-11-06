"""Catálogo de estrategias definidas como datos (ver reglas.py).

  estrategias/       las que vienen con la app (se actualizan con cada versión publicada)
  mis_estrategias/   las que agregaste vos desde el laboratorio (no se tocan al actualizar)

Cada archivo .json es una estrategia. Una definición inválida se ignora (y queda anotada en PROBLEMAS).
"""
import json
import os

import reglas

RAIZ = os.path.dirname(os.path.abspath(__file__))
CARPETAS = ("estrategias", "mis_estrategias")
DEFINICIONES = {}  # id -> definición
PROBLEMAS = {}     # archivo -> problemas encontrados


def _leer(carpeta):
    out = []
    p = os.path.join(RAIZ, carpeta)
    if not os.path.isdir(p):
        return out
    for f in sorted(os.listdir(p)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(p, f), encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError) as e:
            PROBLEMAS[f"{carpeta}/{f}"] = [str(e)]
            continue
        prob = reglas.validar(d)
        if prob:
            PROBLEMAS[f"{carpeta}/{f}"] = prob
            continue
        d["_origen"] = carpeta
        out.append(d)
    return out


def cargar(strats, nombres):
    """Registra las estrategias del catálogo en el motor. Las de código (las 6 originales) no se pisan."""
    DEFINICIONES.clear(); PROBLEMAS.clear()
    for carpeta in CARPETAS:
        for d in _leer(carpeta):
            if d["id"] in strats and "datos" not in strats[d["id"]]:
                PROBLEMAS[d["id"]] = ["el id ya lo usa una estrategia incorporada"]
                continue
            strats[d["id"]] = reglas.compilar(d)
            nombres[d["id"]] = d.get("nombre", d["id"])
            DEFINICIONES[d["id"]] = d


def nombre(d, lang):
    return d.get("nombre_en") if lang == "en" and d.get("nombre_en") else d.get("nombre", d["id"])


def descripcion(d, lang):
    txt = d.get("descripcion_en") if lang == "en" and d.get("descripcion_en") else d.get("descripcion")
    return txt or reglas.describir(d)


def guardar_propia(d):
    """Copia una estrategia (por ejemplo, una candidata del laboratorio) a mis_estrategias."""
    os.makedirs(os.path.join(RAIZ, "mis_estrategias"), exist_ok=True)
    d = {k: v for k, v in d.items() if not k.startswith("_")}
    with open(os.path.join(RAIZ, "mis_estrategias", d["id"] + ".json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def quitar_propia(id_):
    p = os.path.join(RAIZ, "mis_estrategias", id_ + ".json")
    if os.path.exists(p):
        os.remove(p)
