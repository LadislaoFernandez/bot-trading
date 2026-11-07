"""Arma todo lo que muestra la aplicación a partir de los archivos del bot y los precios en vivo.

No depende de la interfaz gráfica, así se puede probar por separado.
"""
import csv
import json
import math
import os
import time
from datetime import datetime

import config as K
from i18n import num, t

NOMBRES = __import__("engine").NOMBRES  # un solo registro de estrategias (engine + catálogo)
MOTIVOS = {"stop": "Stop", "salida_señal": "Señal de salida", "reversa": "Cambio de dirección",
           "fin_backtest": "Fin de período", "cierre_manual": "Cierre manual", "sin_stop": "Sin stop en Binance"}


def _nombre(s):
    import mercado
    return mercado.nombre_estrategia(s)


def fmt(v, d=2, signo=False):
    """Número en el formato del idioma elegido."""
    return num(v, d, signo)


def fmt_precio(v):
    if v is None:
        return "—"
    return fmt(v, 2 if v >= 100 else 3 if v >= 1 else 5)


def fmt_dur(seg):
    seg = int(max(0, seg))
    d, r = divmod(seg, 86400)
    h, r = divmod(r, 3600)
    m, _ = divmod(r, 60)
    if d:
        return f"{d} d {h} h"
    if h:
        return f"{h} h {m} min"
    return f"{m} min"


def fecha_corta(txt):
    """'2026-11-05 18:00' -> '05/11 18:00'"""
    try:
        return datetime.strptime(txt, "%Y-%m-%d %H:%M").strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return txt or "—"


def leer_ajustes(carpeta="."):
    try:
        with open(os.path.join(carpeta, "ajustes.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def leer_estado(carpeta="."):
    p = os.path.join(carpeta, K.STATE_FILE)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def leer_csv(nombre, carpeta="."):
    p = os.path.join(carpeta, nombre)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def leer_log(carpeta=".", lineas=400):
    p = os.path.join(carpeta, K.LOG_FILE)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", errors="replace") as f:
        return [l.rstrip("\n") for l in f.readlines()[-lineas:]]


def _base_fila(r):
    """Capital del modo anotado en la fila (las filas viejas no lo tienen; en un archivo con encabezado viejo llega
    como columna sin nombre)."""
    b = r.get("base") or (r.get(None) or [None])[0]
    try:
        return float(b) if b not in (None, "") else None
    except ValueError:
        return None


def curva_capital_archivo(carpeta, archivo):
    """[(hora, saldo, capital del modo o None)] de un archivo de saldo horario."""
    pts = []
    for r in leer_csv(archivo, carpeta):
        try:
            pts.append((datetime.strptime(r["hora"], "%Y-%m-%d %H:%M").timestamp(), float(r["total"]), _base_fila(r)))
        except (KeyError, ValueError):
            continue
    return pts


def meses_de(pts):
    """Resultado de cada mes y caída máxima total, sin contar los cambios de capital del modo como ganancia o pérdida.
    pts: [(hora, saldo, capital del modo o None)]. Sin el capital anotado (filas viejas), un salto de más del 10 % en
    una hora, hacia arriba o hacia abajo, se toma como cambio de capital: el bot no se mueve tanto en una hora."""
    meses, indice, prev, pico, dd = [], 1.0, None, 1.0, 0.0
    for p in pts:
        ts, v = p[0], p[1]
        b = p[2] if len(p) > 2 else None
        if prev is not None and prev[1] > 0 and v > 0:
            if b and prev[2]:
                r = (v / b) / (prev[1] / prev[2])
            else:
                r = v / prev[1]
                if abs(math.log(r)) > math.log(1.10):  # igual hacia arriba y hacia abajo: 300 -> 350 -> 300 no es ganancia ni pérdida
                    r = 1.0
            indice *= r
        prev = (ts, v, b)
        m = datetime.fromtimestamp(ts).strftime("%Y-%m")
        if not meses or meses[-1]["mes"] != m:
            meses.append(dict(mes=m, i0=meses[-1]["i1"] if meses else indice, i1=indice, ipico=indice, fin=v, dd=0.0))
        x = meses[-1]
        x["i1"] = indice; x["fin"] = v; x["ipico"] = max(x["ipico"], indice)
        x["dd"] = max(x["dd"], (1 - indice / x["ipico"]) * 100)
        pico = max(pico, indice); dd = max(dd, (1 - indice / pico) * 100)
    for x in meses:
        x["pct"] = (x["i1"] / x["i0"] - 1) * 100 if x["i0"] else None
    return meses, dd


def resultados_mensuales(carpeta="."):
    """Resultado de cada mes del modo actual (saldo al cierre, variación, caída máxima del mes) y la caída máxima total."""
    return meses_de(curva_capital_archivo(carpeta, K.EQUITY_FILE))


def curva_capital(carpeta=".", max_puntos=1500):
    filas = leer_csv(K.EQUITY_FILE, carpeta)
    pts = []
    for r in filas:
        try:
            pts.append((datetime.strptime(r["hora"], "%Y-%m-%d %H:%M").timestamp(), float(r["total"])))
        except (KeyError, ValueError):
            continue
    if max_puntos and len(pts) > max_puntos:
        paso = len(pts) / max_puntos
        pts = [pts[int(i * paso)] for i in range(max_puntos)] + [pts[-1]]
    return pts


def operaciones(carpeta="."):
    out = []
    for r in leer_csv(K.TRADES_FILE, carpeta):
        try:
            a, s = r["posicion"].split("_", 1)
            out.append(dict(activo=a, estrategia=_nombre(s), clave=s, lado=r["side"],
                            entrada_t=r["entrada_t"], salida_t=r["salida_t"],
                            entrada=float(r["entrada"]), salida=float(r["salida"]),
                            cantidad=float(r["cantidad"]), pnl=float(r["pnl"]),
                            motivo=t(MOTIVOS.get(r["motivo"], r["motivo"])), capital=float(r["capital"])))
        except (KeyError, ValueError):
            continue
    return out[::-1]  # la más reciente primero


def decisiones(carpeta=".", max_rev=72):
    p = os.path.join(carpeta, K.DECISIONES_FILE)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        lineas = f.readlines()[-max_rev:]
    out = []
    for l in reversed(lineas):  # la más reciente primero
        try:
            out.append(json.loads(l))
        except ValueError:
            continue
    return out


def snapshot(carpeta=".", precios=None, status=None):
    """Todo lo que necesita la interfaz en un solo diccionario."""
    precios = precios or {}
    status = status or {}
    st = leer_estado(carpeta)
    activas = (st or {}).get("activas") or list(K.STRATEGIES)
    aj = leer_ajustes(carpeta)
    asig = aj.get("asignacion", {}).get(K.MODO)
    auto = bool(aj.get("auto", {}).get("activo"))
    ef = (st or {}).get("efectivo") or {}
    act_mon = ef.get("activas") or {a: activas for a in K.SYMBOLS}
    asig_ef = ef.get("asignacion") or {k: v for k, v in (asig or {}).items() if k.split("_", 1)[1] in activas}
    por_parte = K.INITIAL_CAPITAL / (len(K.SYMBOLS) * len(K.STRATEGIES))
    filas, realizado_cap, abierto = [], 0.0, 0.0
    for a in K.SYMBOLS:
        for s in NOMBRES:
            defecto = {"equity": por_parte if s in K.STRATEGIES and st is None else 0.0, "pos": None, "pending": None}
            ss = (st or {}).get("sleeves", {}).get(f"{a}_{s}", defecto)
            usa = s in act_mon.get(a, [])
            if not ss.get("pos") and ss["equity"] <= 1e-9 and not usa:
                continue  # estrategia apagada y sin nada en esta moneda (las activas se muestran aunque tengan 0)
            p, px = ss.get("pos"), precios.get(a, {}).get("precio")
            fila = dict(activo=a, estrategia=_nombre(s), clave=s, activa=usa,
                        asignado=asig_ef.get(f"{a}_{s}", 0.0) if usa else 0.0,
                        capital=ss["equity"], resultado=0.0,
                        pendiente=ss.get("pending"), lado=None, entrada=None, stop=None, precio=px, tamano=None,
                        pnl=None, pnl_pct=None, dist_stop_pct=None, riesgo=None, abierta_desde=None)
            if p:
                sg = 1 if p["side"] == "long" else -1
                fila.update(lado=p["side"], entrada=p["e"], stop=p["stop"], tamano=p["q"] * p["e"],
                            riesgo=sg * (p["e"] - p["stop"]) * p["q"],
                            abierta_desde=p.get("t", 0) / 1000 if p.get("t") else None)
                if px:
                    fila["pnl"] = sg * (px - p["e"]) * p["q"]
                    fila["pnl_pct"] = sg * (px / p["e"] - 1) * 100
                    fila["dist_stop_pct"] = sg * (px - p["stop"]) / px * 100
                    abierto += fila["pnl"]
            realizado_cap += ss["equity"]
            filas.append(fila)

    libre = (st or {}).get("libre", 0.0)
    base = (((st or {}).get("capital_inicial") or K.INITIAL_CAPITAL) + (st or {}).get("aportes", 0.0)) if st else K.INITIAL_CAPITAL
    ops = operaciones(carpeta)
    for f in filas:  # resultado de cada parte = suma de sus operaciones cerradas
        f["resultado"] = sum(o["pnl"] for o in ops if o["activo"] == f["activo"] and o["estrategia"] == f["estrategia"])
    ganadas = [o for o in ops if o["pnl"] > 0]
    total = realizado_cap + abierto + libre
    return dict(
        hay_estado=st is not None,
        inicio=(st or {}).get("inicio"),
        saldo=total,
        saldo_cerrado=realizado_cap + libre,
        libre=libre,
        base=base,
        asignacion=asig or {},
        asignacion_efectiva=asig_ef if auto else {},
        frenado=(st or {}).get("frenado", False),
        rendimiento_pct=(total / base - 1) * 100 if base else 0.0,
        realizado=realizado_cap + libre - base,
        abierto=abierto,
        posiciones=filas,
        abiertas=[f for f in filas if f["lado"]],
        operaciones=ops,
        resumen_ops=dict(n=len(ops), ganadas=len(ganadas),
                         pct=(len(ganadas) / len(ops) * 100) if ops else None,
                         pnl=sum(o["pnl"] for o in ops),
                         mejor=max((o["pnl"] for o in ops), default=None),
                         peor=min((o["pnl"] for o in ops), default=None)),
        curva=curva_capital(carpeta),
        activas=activas,
        auto=auto,
        auto_estado=(st or {}).get("auto"),
        ordenes=(st or {}).get("ordenes"),
        mensual=resultados_mensuales(carpeta),
        activas_moneda=act_mon,
        decisiones=decisiones(carpeta),
        precios=precios,
        status=dict(status),
        ahora=time.time(),
    )
