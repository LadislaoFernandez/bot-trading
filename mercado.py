"""Análisis del mercado en vivo e historial de cada estrategia según el tipo de mercado.

Tipo de mercado (en velas de 1 hora, solo con información ya cerrada):
  - Tendencia alcista: ADX >= 20 y EMA 50 sobre EMA 200
  - Tendencia bajista: ADX >= 20 y EMA 50 bajo EMA 200
  - Lateral: ADX < 20
Volatilidad: ATR actual contra la mediana de los últimos 30 días (alta > 1,3 veces, baja < 0,8 veces).

El historial se calcula corriendo cada estrategia sobre velas reales desde 2022 con las mismas reglas,
riesgo y comisiones que usa el bot, y anotando en qué tipo de mercado se abrió cada operación.
"""
import json
import os
import time
from datetime import datetime, timezone

import config as K
from engine import STRATS, Sleeve, prepare
from i18n import t as _t

PT_NOMBRES = __import__("engine").NOMBRES  # un solo registro de estrategias (engine + catálogo)

CACHE = "historial_estrategias.json"
REGIMENES = ["Tendencia alcista", "Tendencia bajista", "Lateral"]
DESDE = "2022-01-01"
MIN_OPS = 30          # mínimo de operaciones para considerar el dato confiable
PF_RECOMENDABLE = 1.10
DIAS_RECIENTE = 90    # ventana para ver si una estrategia viene empeorando
MIN_OPS_RECIENTE = 10
PF_EMPEORA = 0.90     # con menos de esto en los últimos 90 días (y bien en el total), se considera que empeora


def nombre_estrategia(s):
    """Nombre para mostrar, también de las estrategias del catálogo (con su nombre en inglés si lo tienen)."""
    import catalogo
    import i18n
    if s in catalogo.DEFINICIONES:
        return catalogo.nombre(catalogo.DEFINICIONES[s], i18n.LANG)
    return _t(PT_NOMBRES.get(s, s))


def regimen(D, i):
    if D["ADX"][i] < 20:
        return "Lateral"
    return "Tendencia alcista" if D["EMA50"][i] > D["EMA200"][i] else "Tendencia bajista"


def volatilidad(D, i, ventana=720):
    a = [D["ATR"][k] / D["C"][k] for k in range(max(1, i - ventana), i + 1)]
    med = sorted(a)[len(a) // 2]
    r = a[-1] / med if med else 1
    return ("Alta" if r > 1.3 else "Baja" if r < 0.8 else "Normal"), r


def analisis(D):
    """Lectura del mercado en la última vela cerrada."""
    i = D["n"] - 1
    C = D["C"][i]
    reg = regimen(D, i)
    vol, ratio = volatilidad(D, i)
    hi, lo = D["DH48"][i], D["DL48"][i]
    pos48 = (C - lo) / (hi - lo) * 100 if hi > lo else 50
    var24 = (C / D["C"][max(0, i - 24)] - 1) * 100
    tend4h = "alcista" if D["trend"][i] > 0 else "bajista" if D["trend"][i] < 0 else "sin definir"
    from i18n import num, t
    adx = num(D["ADX"][i], 1)
    if reg == "Lateral":
        resumen = t("Sin tendencia clara (ADX {a}, por debajo de 20). El precio se mueve dentro de un rango.", a=adx)
    elif reg == "Tendencia alcista":
        resumen = t("El mercado sube con fuerza (ADX {a}). La media de 50 horas está por encima de la de 200.", a=adx)
    else:
        resumen = t("El mercado baja con fuerza (ADX {a}). La media de 50 horas está por debajo de la de 200.", a=adx)
    resumen += " " + t("Volatilidad {v}: {r} veces lo habitual del último mes.", v=t(vol).lower(), r=num(ratio, 2))
    return dict(regimen=reg, volatilidad=vol, vol_ratio=ratio, adx=D["ADX"][i], rsi=D["RSI14"][i],
                tendencia_4h=tend4h, pos_rango48=pos48, var24=var24, precio=C, resumen=resumen, atr_pct=D["ATR"][i] / C,
                hora=D["T"][i] / 1000)


# ------------------------------------------------------------------ historial por régimen
def _correr(D, strat, desde_ms):
    sl, ops, eq_entrada, reg_entrada = Sleeve(strat, K.RISK_PER_TRADE, K.MAX_LEVERAGE, K.FEE, K.SLIPPAGE, 100.0), [], None, None
    for i in range(1, D["n"]):
        if D["T"][i] < desde_ms:
            continue
        tenia = sl.pos is not None
        eq_antes = sl.equity
        reg_vela_anterior = regimen(D, i - 1)  # la orden pendiente se decidió al cierre de la vela anterior
        sl.on_bar(D, i)
        if not tenia and sl.pos is not None:  # abrió en la apertura de esta vela
            eq_entrada, reg_entrada = eq_antes, reg_vela_anterior
        for tr in sl.closed:
            base = eq_entrada or eq_antes
            ops.append((reg_entrada or reg_vela_anterior, tr["pnl"] / base * 100, tr["entrada_t"]))
            eq_entrada = reg_entrada = None
            if sl.pos is not None:  # se dio vuelta en la misma vela
                eq_entrada, reg_entrada = sl.equity, reg_vela_anterior
        sl.closed = []
    return ops, sl.equity


def calcular_historial(fetch_rows, progreso=None):
    """fetch_rows(asset) -> velas 1h desde 2021-12. Devuelve el resumen por estrategia y régimen."""
    desde_ms = int(datetime.strptime(DESDE, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    acum = {s: {r: [] for r in REGIMENES} for s in STRATS}
    recientes = {s: [] for s in STRATS}
    total = {s: [] for s in STRATS}
    desde_rec = int(time.time() * 1000) - DIAS_RECIENTE * 86400 * 1000
    pasos = len(K.SYMBOLS) * (len(STRATS) + 1)
    n = 0
    for a in K.SYMBOLS:
        if progreso:
            progreso(n / pasos, _t("Bajando historial de {a}", a=a))
        D = prepare(fetch_rows(a), K.BAR_MS, K.HTF_MS)
        n += 1
        for s in STRATS:
            if progreso:
                progreso(n / pasos, _t("Probando {s} en {a}", s=nombre_estrategia(s), a=a))
            ops, eq = _correr(D, s, desde_ms)
            for r, pct, t_ent in ops:
                acum[s][r].append(pct)
                if t_ent >= desde_rec:
                    recientes[s].append(pct)
            total[s].append(eq / 100 - 1)
            n += 1
    out = {"calculado": time.time(), "desde": DESDE, "estrategias": {}}
    for s in STRATS:
        por_reg = {}
        for r in REGIMENES + ["Total"]:
            xs = [x for rr in REGIMENES for x in acum[s][rr]] if r == "Total" else acum[s][r]
            por_reg[r] = _resumen(xs)
        rec = _resumen(recientes[s])
        out["estrategias"][s] = dict(regimenes=por_reg, reciente=rec, estado=_estado(por_reg["Total"], rec),
                                     resultado_prom_activo=sum(total[s]) / len(total[s]) * 100 if total[s] else None)
    return out


def _resumen(xs):
    g, p = sum(x for x in xs if x > 0), -sum(x for x in xs if x <= 0)
    return dict(ops=len(xs), ganadoras=(sum(1 for x in xs if x > 0) / len(xs) * 100) if xs else None,
                promedio=(sum(xs) / len(xs)) if xs else None, pf=(g / p) if p > 0 else (None if not g else 99.0))


def _estado(total, rec):
    """'empeora' si funcionaba en el total pero en los últimos 90 días perdió más de lo que ganó; si no, 'normal'."""
    ok_total = (total.get("ops") or 0) >= MIN_OPS and (total.get("pf") or 0) >= PF_RECOMENDABLE
    if ok_total and (rec.get("ops") or 0) >= MIN_OPS_RECIENTE and rec.get("pf") is not None and rec["pf"] < PF_EMPEORA:
        return "empeora"
    return "normal"


def estado(historial, estrategia):
    return ((historial or {}).get("estrategias", {}).get(estrategia) or {}).get("estado", "normal")


def comparar(anterior, nuevo):
    """Cambios de estado entre dos historiales: lista de (estrategia, 'empeora' | 'recupera')."""
    out = []
    for s, d in (nuevo or {}).get("estrategias", {}).items():
        antes, ahora = estado(anterior, s), d.get("estado", "normal")
        if ahora == "empeora" and antes != "empeora":
            out.append((s, "empeora"))
        elif antes == "empeora" and ahora != "empeora":
            out.append((s, "recupera"))
    return out


def guardar(h, carpeta="."):
    with open(os.path.join(carpeta, CACHE), "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=1)


def cargar(carpeta="."):
    try:
        with open(os.path.join(carpeta, CACHE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def recomendar(historial, reg):
    """Ranking de estrategias para el tipo de mercado actual, de mejor a peor."""
    if not historial:
        return []
    filas = []
    for s, d in historial["estrategias"].items():
        if s not in STRATS:  # estrategia que ya no está instalada
            continue
        r = d["regimenes"].get(reg, {})
        ok = (r.get("ops") or 0) >= MIN_OPS and r.get("pf") is not None
        empeora = d.get("estado") == "empeora"
        filas.append(dict(estrategia=s, ops=r.get("ops") or 0, pf=r.get("pf"), ganadoras=r.get("ganadoras"),
                          promedio=r.get("promedio"), confiable=ok, empeora=empeora,
                          recomendable=ok and r["pf"] >= PF_RECOMENDABLE and not empeora))
    filas.sort(key=lambda f: (f["confiable"], f["pf"] or 0), reverse=True)
    return filas


def evaluar(historial, estrategia, regimen_por_activo):
    """Recomendación de una estrategia para el mercado actual de cada moneda.
    Devuelve (nivel, texto): nivel = 'si', 'debil', 'no' o 'sin_datos'."""
    from i18n import num, t
    if not historial or estrategia not in historial.get("estrategias", {}):
        return "sin_datos", t("La recomendación aparece cuando termine de calcularse el historial.")
    grupos = {}
    for a, r in regimen_por_activo.items():
        grupos.setdefault(r, []).append(a)
    frases, niveles = [], []
    for r, activos in grupos.items():
        d = historial["estrategias"][estrategia]["regimenes"].get(r, {})
        ops, pf = d.get("ops") or 0, d.get("pf")
        act = t(" y ").join([", ".join(activos[:-1]), activos[-1]]) if len(activos) > 1 else activos[0]
        reg = t(r).lower()
        if ops < MIN_OPS or pf is None:
            niveles.append("sin_datos")
            frases.append(t("{a} ({r}): con {n} operaciones en este tipo de mercado no hay datos suficientes para "
                            "saber si conviene.", a=act, r=reg, n=ops))
        elif pf >= PF_RECOMENDABLE:
            niveles.append("si")
            frases.append(t("Conviene en {a} ({r}): en este tipo de mercado ganó {pf} veces lo que perdió, en {n} "
                            "operaciones.", a=act, r=reg, pf=num(pf), n=ops))
        elif pf >= 1:
            niveles.append("debil")
            frases.append(t("No conviene en {a} ({r}): ganó apenas {pf} veces lo que perdió en {n} operaciones, una "
                            "ventaja demasiado chica para cubrir comisiones y errores de ejecución.", a=act, r=reg,
                            pf=num(pf), n=ops))
        else:
            niveles.append("no")
            frases.append(t("No conviene en {a} ({r}): en este tipo de mercado perdió más de lo que ganó ({pf} en {n} "
                            "operaciones).", a=act, r=reg, pf=num(pf), n=ops))
    nivel = "si" if "si" in niveles else "no" if "no" in niveles else "debil" if "debil" in niveles else "sin_datos"
    d = historial["estrategias"][estrategia]
    if d.get("estado") == "empeora":
        rec = d.get("reciente", {})
        frases.insert(0, t("Viene empeorando: en los últimos {d} días perdió más de lo que ganó ({pf} en {n} "
                           "operaciones). El piloto automático no la usa hasta que se recupere.", d=DIAS_RECIENTE,
                           pf=num(rec.get("pf")), n=rec.get("ops")))
        nivel = "no"
    return nivel, " ".join(frases)
