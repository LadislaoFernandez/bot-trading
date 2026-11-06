"""Escritura segura de archivos en Windows.

Windows no deja reemplazar un archivo mientras otro proceso lo tiene abierto (la app lee el estado cada pocos
segundos, el laboratorio corre en otro proceso). Por eso se escribe a un temporal propio de cada proceso y se
reintenta el reemplazo unos segundos antes de rendirse.
"""
import json
import os
import threading
import time


def reemplazar(tmp, destino, segundos=5.0):
    fin = time.time() + segundos
    while True:
        try:
            os.replace(tmp, destino)
            return
        except PermissionError:
            if time.time() >= fin:
                raise
            time.sleep(0.05)


def escribir_json(destino, datos, **kw):
    tmp = f"{destino}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, **kw)
    reemplazar(tmp, destino)


def leer_json(ruta, defecto=None, segundos=2.0):
    """Lee un JSON reintentando si otro proceso lo está reemplazando justo en ese momento."""
    fin = time.time() + segundos
    while True:
        try:
            with open(ruta, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return defecto
        except (PermissionError, ValueError):
            if time.time() >= fin:
                return defecto
            time.sleep(0.05)
