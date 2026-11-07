"""Análisis del mercado en vivo e historial de cada estrategia según el tipo de mercado.

Tipo de mercado (en velas de 1 hora, solo con información ya cerrada):
  - Tendencia alcista: ADX >= 20 y EMA 50 sobre EMA 200
  - Tendencia bajista: ADX >= 20 y EMA 50 bajo EMA 200
  - Lateral: ADX < 20
Volatilidad: ATR actual contra la mediana de los últimos 30 días (alta > 1,3 veces, baja < 0,8 veces).

El tipo de mercado se muestra como información: el piloto automático no lo usa para elegir estrategias (en las
simulaciones de 2023 a 2026, prender y apagar estrategias según el tipo de mercado perdía contra dejarlas fijas).

El historial se calcula corriendo cada estrategia sobre velas reales desde 2022 con las mismas reglas, riesgo y
comisiones que usa el bot: resultado por año, por mes y por semestre (lo que mira la revisión mensual del piloto).
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


# ------------------------------------------------------------------ historial de cada estrategia



def _correr(D, strat, desde_ms):
    """Corre la estrategia en todas las velas desde desde_ms. Devuelve las operaciones (régimen al entrar, % sobre el
    capital, hora de entrada, hora de salida), el capital final (empezando con 100) y el capital al cierre de cada mes."""
    sl, ops, eq_entrada, reg_entrada = Sleeve(strat, K.RISK_PER_TRADE, K.MAX_LEVERAGE, K.FEE, K.SLIPPAGE, 100.0), [], None, None
    meses = {}
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
            ops.append((reg_entrada or reg_vela_anterior, tr["pnl"] / base * 100, tr["entrada_t"], tr["salida_t"]))
            eq_entrada = reg_entrada = None
            if sl.pos is not None:  # se dio vuelta en la misma vela
                eq_entrada, reg_entrada = sl.equity, reg_vela_anterior
        sl.closed = []
        meses[datetime.fromtimestamp(D["T"][i] / 1000, timezone.utc).strftime("%Y-%m")] = sl.mark(D["C"][i])
    return ops, sl.equity, meses


def semestres_de(mensual, ahora=None):
    """Resultado de los últimos 4 semestres completos (el más reciente primero), con el capital de la estrategia
    siempre prendida, en promedio de las 3 monedas. mensual: {"2026-09": % del mes}. El mes en curso no cuenta."""
    ahora = ahora or datetime.now(timezone.utc)
    y, m = ahora.year, ahora.month
    meses = []
    for _ in range(24):  # los 24 meses completos anteriores al actual
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        meses.append(f"{y}-{m:02d}")
    out = []
    for q in range(4):
        bloque = meses[q * 6:(q + 1) * 6]
        if any(b not in mensual for b in bloque):
            break
        r = 1.0
        for b in bloque:
            r *= 1 + mensual[b] / 100
        out.append((r - 1) * 100)
    return out


def calcular_historial(fetch_rows, progreso=None, ahora_ms=None):
    """fetch_rows(asset) -> velas 1h desde 2021-12. Devuelve el resumen de cada estrategia: resultado por año y por mes
    (promedio de las 3 monedas, como si estuviera siempre prendida), los últimos 4 semestres (para la revisión mensual
    del piloto) y el detalle por tipo de mercado."""
    desde_ms = int(datetime.strptime(DESDE, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    ahora_ms = ahora_ms or int(time.time() * 1000)
    estrategias = [s for s in STRATS if s not in getattr(K, "RETIRADAS", ())]
    acum = {s: {r: [] for r in REGIMENES} for s in estrategias}
    todas = {s: [] for s in estrategias}
    meses = {s: {} for s in estrategias}
    pasos = len(K.SYMBOLS) * (len(estrategias) + 1)
    n = 0
    for a in K.SYMBOLS:
        if progreso:
            progreso(n / pasos, _t("Bajando historial de {a}", a=a))
        D = prepare(fetch_rows(a), K.BAR_MS, K.HTF_MS)
        n += 1
        for s in estrategias:
            if progreso:
                progreso(n / pasos, _t("Probando {s} en {a}", s=nombre_estrategia(s), a=a))
            ops, eq, mm = _correr(D, s, desde_ms)
            for o in ops:
                if o[3] < ahora_ms:
                    acum[s][o[0]].append(o[1]); todas[s].append(o)
            prev = 100.0
            for m in sorted(mm):
                meses[s].setdefault(m, []).append(mm[m] / prev - 1)
                prev = mm[m]
            n += 1
    out = {"calculado": time.time(), "desde": DESDE, "version": 2, "estrategias": {}}
    for s in estrategias:
        por_reg = {r: _resumen(acum[s][r]) for r in REGIMENES}
        por_reg["Total"] = _resumen([o[1] for o in todas[s]])
        mensual = {m: sum(v) / len(v) * 100 for m, v in sorted(meses[s].items())}
        anios = {}
        for m, v in mensual.items():
            anios[m[:4]] = (1 + anios.get(m[:4], 0) / 100) * (1 + v / 100) * 100 - 100
        out["estrategias"][s] = dict(regimenes=por_reg, mensual=mensual, anios=anios, semestres=semestres_de(mensual))
    return out


def _resumen(xs):
    g, p = sum(x for x in xs if x > 0), -sum(x for x in xs if x <= 0)
    return dict(ops=len(xs), ganadoras=(sum(1 for x in xs if x > 0) / len(xs) * 100) if xs else None,
                promedio=(sum(xs) / len(xs)) if xs else None, pf=(g / p) if p > 0 else (None if not g else 99.0))


def califica(historial, estrategia):
    """Revisión mensual del piloto: la estrategia califica si ganó plata en los últimos 12 meses (los 2 semestres más
    recientes). Solo se juzga con al menos 2 años de historial (4 semestres): con menos, un solo año malo la sacaría.
    Devuelve (califica, semestres): califica es None si todavía no hay historial suficiente."""
    d = ((historial or {}).get("estrategias", {}) or {}).get(estrategia)
    rs = (d or {}).get("semestres") or []
    if len(rs) < 4:
        return None, rs
    return ((1 + rs[0] / 100) * (1 + rs[1] / 100) - 1) > 0, rs


def ultimo_anio(rs):
    return ((1 + rs[0] / 100) * (1 + rs[1] / 100) - 1) * 100 if len(rs) >= 2 else None


def guardar(h, carpeta="."):
    with open(os.path.join(carpeta, CACHE), "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=1)


def cargar(carpeta="."):
    try:
        with open(os.path.join(carpeta, CACHE), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
