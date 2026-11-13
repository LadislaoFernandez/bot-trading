"""Indicadores, estrategias y gestión de posición.

Es una traducción línea por línea del motor JavaScript con el que se hicieron los backtests,
para que el bot en vivo tome exactamente las mismas decisiones.
"""
import math

NAN = float("nan")


# ---------------------------------------------------------------- indicadores
def _ema(x, p):
    a, y = 2 / (p + 1), [0.0] * len(x)
    for i, v in enumerate(x):
        y[i] = (1 - a) * y[i - 1] + a * v if i else v
    return y


def _rma(x, p):
    a, y = 1 / p, [0.0] * len(x)
    for i, v in enumerate(x):
        y[i] = (1 - a) * y[i - 1] + a * v if i else v
    return y


def _gt(a, b):  # comparación estilo JS: con NaN da False
    return a > b if not (math.isnan(a) or math.isnan(b)) else False


def _lt(a, b):
    return a < b if not (math.isnan(a) or math.isnan(b)) else False


def _sign(v):
    return NAN if math.isnan(v) else (1.0 if v > 0 else -1.0 if v < 0 else 0.0)


def prepare(rows, bar_ms, htf_ms):
    """rows: [[ms, open, high, low, close], ...] ordenadas y solo velas cerradas."""
    n = len(rows)
    T = [r[0] for r in rows]; O = [float(r[1]) for r in rows]; H = [float(r[2]) for r in rows]
    L = [float(r[3]) for r in rows]; C = [float(r[4]) for r in rows]
    TR = [H[i] - L[i] if i == 0 else max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(n)]
    pdm, mdm = [0.0] * n, [0.0] * n
    for i in range(1, n):
        up, dn = H[i] - H[i - 1], L[i - 1] - L[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
    trS, pS, mS = _rma(TR, 14), _rma(pdm, 14), _rma(mdm, 14)
    dx = [0.0] * n
    for i in range(n):
        if trS[i] == 0:
            continue
        p, m = 100 * pS[i] / trS[i], 100 * mS[i] / trS[i]
        s = p + m
        dx[i] = 0.0 if s == 0 or not math.isfinite(s) else 100 * abs(p - m) / s
    ADX, ATR = _rma(dx, 14), _rma(TR, 14)
    gain, loss = [0.0] * n, [0.0] * n
    for i in range(1, n):
        d = C[i] - C[i - 1]
        gain[i], loss[i] = (d if d > 0 else 0.0), (-d if d < 0 else 0.0)

    def rsi(p):
        g, l = _rma(gain, p), _rma(loss, p)
        return [100.0 if l[i] == 0 else 100 - 100 / (1 + g[i] / l[i]) for i in range(n)]

    RSI14, RSI2 = rsi(14), rsi(2)
    # Supertrend (ATR 10, multiplicador 3): +1 alcista, -1 bajista
    atr10, ST = _rma(TR, 10), [1.0] * n
    fu, fl = [0.0] * n, [0.0] * n
    for i in range(n):
        hl2 = (H[i] + L[i]) / 2
        bu, bl = hl2 + 3 * atr10[i], hl2 - 3 * atr10[i]
        if i == 0:
            fu[i], fl[i] = bu, bl
            continue
        fu[i] = bu if (bu < fu[i - 1] or C[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = bl if (bl > fl[i - 1] or C[i - 1] < fl[i - 1]) else fl[i - 1]
        if ST[i - 1] < 0:
            ST[i] = 1.0 if C[i] > fu[i] else -1.0
        else:
            ST[i] = -1.0 if C[i] < fl[i] else 1.0

    def sma(x, p):
        y, s = [NAN] * n, 0.0
        for i in range(n):
            s += x[i]
            if i >= p:
                s -= x[i - p]
            if i >= p - 1:
                y[i] = s / p
        return y

    def sd(x, p, m):
        y, s2 = [NAN] * n, 0.0
        for i in range(n):
            s2 += x[i] * x[i]
            if i >= p:
                s2 -= x[i - p] * x[i - p]
            if i >= p - 1:
                y[i] = math.sqrt(max(0.0, s2 / p - m[i] * m[i]))
        return y

    def rmax(x, p):
        return [NAN] * (p - 1) + [max(x[i - p + 1:i + 1]) for i in range(p - 1, n)] if n >= p else [NAN] * n

    def rmin(x, p):
        return [NAN] * (p - 1) + [min(x[i - p + 1:i + 1]) for i in range(p - 1, n)] if n >= p else [NAN] * n

    SMA20 = sma(C, 20); SD20 = sd(C, 20, SMA20); trM = sma(TR, 20); SMA5 = sma(C, 5)
    HH20, LL20, DH48, DL48 = rmax(H, 20), rmin(L, 20), rmax(H, 48), rmin(L, 48)
    sqz = [(SMA20[i] - 2 * SD20[i]) > (SMA20[i] - 1.5 * trM[i]) and (SMA20[i] + 2 * SD20[i]) < (SMA20[i] + 1.5 * trM[i])
           if not math.isnan(SMA20[i]) else False for i in range(n)]
    src = [C[i] - ((HH20[i] + LL20[i]) / 2 + SMA20[i]) / 2 for i in range(n)]
    V = [NAN] * n
    for i in range(38, n):
        w = src[i - 19:i + 1]
        if any(not math.isfinite(v) for v in w):
            continue
        sx = sy = sxx = sxy = 0.0
        for x, yv in enumerate(w):
            sx += x; sy += yv; sxx += x * x; sxy += x * yv
        sl = (20 * sxy - sx * sy) / (20 * sxx - sx * sx)
        V[i] = sl * 19 + (sy - sl * sx) / 20

    periods = {}
    for i in range(n):
        periods[(T[i] // htf_ms) * htf_ms] = C[i]
    dK = sorted(periods); dC = [periods[k] for k in dK]; dF, dS = _ema(dC, 10), _ema(dC, 55)
    trend, j = [NAN] * n, -1
    for i in range(n):
        while j + 1 < len(dK) and dK[j + 1] + htf_ms <= T[i]:
            j += 1
        if j >= 0:
            trend[i] = _sign(dF[j] - dS[j])

    return dict(n=n, T=T, O=O, H=H, L=L, C=C, ADX=ADX, ATR=ATR, V=V, sqz=sqz, trend=trend,
                EMA20=_ema(C, 20), EMA50=_ema(C, 50), EMA200=_ema(C, 200), DH48=DH48, DL48=DL48,
                RSI14=RSI14, RSI2=RSI2, SMA20=SMA20, SD20=SD20, SMA5=SMA5, ST=ST,
                BBU=[m + 2 * d for m, d in zip(SMA20, SD20)], BBL=[m - 2 * d for m, d in zip(SMA20, SD20)])


# ---------------------------------------------------------------- estrategias
def entry_TL(D, i):
    V = D["V"]
    if i < 55:
        return None
    if not (_gt(V[i], V[i - 1]) and not _gt(V[i - 1], V[i - 2])):
        return None
    if not (D["ADX"][i - 1] - D["ADX"][i - 4] < 0):
        return None
    if not any(D["sqz"][q] for q in range(max(0, i - 6), i + 1)):
        return None
    return "long" if _gt(D["trend"][i], 0) else None


def exit_TL(D, i, side):
    V = D["V"]
    if side == "long":
        return _lt(V[i], 0) and not _lt(V[i - 1], 0) and not math.isnan(V[i - 1])
    return _gt(V[i], 0) and not _gt(V[i - 1], 0) and not math.isnan(V[i - 1])


def entry_BREAKOUT(D, i):
    if i < 200:
        return None
    C, e50, e200 = D["C"][i], D["EMA50"][i], D["EMA200"][i]
    if _gt(C, D["DH48"][i - 1]) and e50 > e200:
        return "long"
    if _lt(C, D["DL48"][i - 1]) and e50 < e200:
        return "short"
    return None


def entry_MR(D, i):
    if i < 200 or not (D["ADX"][i] < 20):
        return None
    lo = D["SMA20"][i] - 2 * D["SD20"][i]
    hi = D["SMA20"][i] + 2 * D["SD20"][i]
    if _lt(D["C"][i], lo) and D["RSI14"][i] < 30:
        return "long"
    if _gt(D["C"][i], hi) and D["RSI14"][i] > 70:
        return "short"
    return None


def exit_MR(D, i, side):
    m = D["SMA20"][i]
    return (D["C"][i] >= m) if side == "long" else (D["C"][i] <= m)


def entry_RSI2(D, i):
    if i < 200:
        return None
    C, e = D["C"][i], D["EMA200"][i]
    if C > e and D["RSI2"][i] < 10:
        return "long"
    if C < e and D["RSI2"][i] > 90:
        return "short"
    return None


def exit_RSI2(D, i, side):
    m = D["SMA5"][i]
    return _gt(D["C"][i], m) if side == "long" else _lt(D["C"][i], m)


def entry_CRUCE(D, i):
    if i < 200:
        return None
    f, s, f1, s1 = D["EMA20"][i], D["EMA50"][i], D["EMA20"][i - 1], D["EMA50"][i - 1]
    if f > s and f1 <= s1 and D["C"][i] > D["EMA200"][i]:
        return "long"
    if f < s and f1 >= s1 and D["C"][i] < D["EMA200"][i]:
        return "short"
    return None


def exit_CRUCE(D, i, side):
    f, s = D["EMA20"][i], D["EMA50"][i]
    return f < s if side == "long" else f > s


def entry_ST(D, i):
    if i < 200:
        return None
    if D["ST"][i] > 0 and D["ST"][i - 1] < 0:
        return "long"
    if D["ST"][i] < 0 and D["ST"][i - 1] > 0:
        return "short"
    return None


def exit_ST(D, i, side):
    return D["ST"][i] < 0 if side == "long" else D["ST"][i] > 0


NOMBRES = {"BREAKOUT": "Breakout", "TL": "Resorte de tendencia", "MR": "Reversión a la media", "RSI2": "RSI(2)",
           "CRUCE": "Cruce de medias", "SUPERTREND": "Supertrend"}  # se completa con el catálogo (catalogo.py)

# be_atr: cuando la operación lleva esa ganancia (en ATR de la entrada), el stop pasa a la entrada + comisiones y ya no
# puede cerrar en pérdida. Simulado 2022-2026: mejora Breakout (252 -> 288 por cada 100) y deja igual al Resorte;
# en Cruce y Supertrend empeora, así que ahí no se usa.
BREAKEVEN_MARGEN = 0.0008  # entrada (maker 0,02 %) + salida del stop (taker 0,05 %) + un poco de margen

STRATS = {
    "TL": dict(entry=entry_TL, exit=exit_TL, stop_atr=2.0, trail_atr=3.0, max_bars=0, be_atr=2.0),
    "BREAKOUT": dict(entry=entry_BREAKOUT, exit=lambda D, i, s: False, stop_atr=2.0, trail_atr=3.0, max_bars=0,
                     be_atr=2.0),
    "MR": dict(entry=entry_MR, exit=exit_MR, stop_atr=2.0, trail_atr=0.0, max_bars=24),
    "RSI2": dict(entry=entry_RSI2, exit=exit_RSI2, stop_atr=3.0, trail_atr=0.0, max_bars=20),
    "CRUCE": dict(entry=entry_CRUCE, exit=exit_CRUCE, stop_atr=2.0, trail_atr=3.0, max_bars=0),
    "SUPERTREND": dict(entry=entry_ST, exit=exit_ST, stop_atr=3.0, trail_atr=3.0, max_bars=0),
}


# ---------------------------------------------------------------- explicación de cada decisión
def _f(v):
    from i18n import num
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return num(v, 2 if abs(v) >= 100 else 3 if abs(v) >= 1 else 5)


def _i(v, d=1):
    from i18n import num
    return "—" if v is None or math.isnan(v) else num(v, d)


def explain(D, i, strat):
    """Condiciones de entrada en la vela i: lista de (texto, se_cumple) para la dirección que se evalúa."""
    from i18n import t
    C = D["C"][i]
    if strat == "BREAKOUT":
        if D["EMA50"][i] > D["EMA200"][i]:
            lim = D["DH48"][i - 1]
            return [(t("Tendencia de fondo alcista (EMA 50 sobre EMA 200)"), True),
                    (t("Cierre {c} por encima del máximo de 48 h ({l})", c=_f(C), l=_f(lim)), _gt(C, lim))]
        lim = D["DL48"][i - 1]
        return [(t("Tendencia de fondo bajista (EMA 50 bajo EMA 200): solo busca ventas en corto"), True),
                (t("Cierre {c} por debajo del mínimo de 48 h ({l})", c=_f(C), l=_f(lim)), _lt(C, lim))]
    if strat == "TL":
        V = D["V"]
        return [(t("Tendencia de 4 h alcista (EMA 10 sobre EMA 55)"), _gt(D["trend"][i], 0)),
                (t("ADX perdiendo fuerza ({a} → {b})", a=_i(D["ADX"][i - 4], 2), b=_i(D["ADX"][i - 1], 2)),
                 D["ADX"][i - 1] - D["ADX"][i - 4] < 0),
                (t("Squeeze en las últimas 6 velas"), any(D["sqz"][q] for q in range(max(0, i - 6), i + 1))),
                (t("Momentum gira hacia arriba en esta vela"), _gt(V[i], V[i - 1]) and not _gt(V[i - 1], V[i - 2]))]
    if strat == "MR":
        lo = D["SMA20"][i] - 2 * D["SD20"][i]; hi = D["SMA20"][i] + 2 * D["SD20"][i]
        cond = [(t("Mercado lateral (ADX {a} menor a 20)", a=_i(D["ADX"][i])), D["ADX"][i] < 20)]
        if abs(C - lo) <= abs(C - hi):
            return cond + [(t("Cierre {c} por debajo de la banda inferior ({l})", c=_f(C), l=_f(lo)), _lt(C, lo)),
                           (t("RSI {r} menor a 30", r=_i(D["RSI14"][i])), D["RSI14"][i] < 30)]
        return cond + [(t("Cierre {c} por encima de la banda superior ({l})", c=_f(C), l=_f(hi)), _gt(C, hi)),
                       (t("RSI {r} mayor a 70", r=_i(D["RSI14"][i])), D["RSI14"][i] > 70)]
    if strat == "RSI2":
        if C > D["EMA200"][i]:
            return [(t("Precio sobre la EMA 200 (solo compras)"), True),
                    (t("RSI(2) {r} menor a 10", r=_i(D["RSI2"][i])), D["RSI2"][i] < 10)]
        return [(t("Precio bajo la EMA 200 (solo ventas en corto)"), True),
                (t("RSI(2) {r} mayor a 90", r=_i(D["RSI2"][i])), D["RSI2"][i] > 90)]
    if strat == "CRUCE":
        f, s_, f1, s1 = D["EMA20"][i], D["EMA50"][i], D["EMA20"][i - 1], D["EMA50"][i - 1]
        if f >= s_:
            return [(t("EMA 20 cruza por encima de la EMA 50 en esta vela"), f > s_ and f1 <= s1),
                    (t("Precio sobre la EMA 200"), C > D["EMA200"][i])]
        return [(t("EMA 20 cruza por debajo de la EMA 50 en esta vela"), f < s_ and f1 >= s1),
                (t("Precio bajo la EMA 200"), C < D["EMA200"][i])]
    if "datos" in STRATS.get(strat, {}):
        import reglas
        return reglas.explicar(STRATS[strat]["datos"], D, i)
    if strat == "SUPERTREND":
        return [(t("Supertrend cambia de dirección en esta vela"), D["ST"][i] != D["ST"][i - 1]),
                (t("Dirección actual: {d}", d=t("alcista") if D["ST"][i] > 0 else t("bajista")), True)]
    return []


# ---------------------------------------------------------------- posición
def asegurar_ganancia(S, p, cierre, atr):
    """Breakeven: con be_atr de ganancia, el stop sube (o baja, en cortos) hasta la entrada más las comisiones."""
    be = S.get("be_atr", 0)
    if not be:
        return
    atr0 = p.get("atr0") or atr  # posiciones abiertas antes de la 1.26 no guardaban el ATR de la entrada
    lg = p["side"] == "long"
    if ((cierre - p["e"]) if lg else (p["e"] - cierre)) >= be * atr0:
        bep = p["e"] * (1 + BREAKEVEN_MARGEN) if lg else p["e"] * (1 - BREAKEVEN_MARGEN)
        p["stop"] = max(p["stop"], bep) if lg else min(p["stop"], bep)


CADA_AJUSTE_STOP = 600  # segundos: entre cierres de vela, el stop se revisa cada 10 minutos
MOVIMIENTO_MINIMO_STOP = 0.001  # cambios menores al 0,1 % del precio de entrada no se mandan a Binance


def stop_seguido(S, p, precio, atr):
    """Stop con las reglas de siempre (trailing a trail_atr del precio y breakeven a be_atr de ganancia) para el
    precio dado y el ATR de la última vela de 1h cerrada. Nunca retrocede. No modifica p."""
    q = dict(p)
    if S["trail_atr"] > 0:
        d = S["trail_atr"] * atr
        q["stop"] = max(q["stop"], precio - d) if q["side"] == "long" else min(q["stop"], precio + d)
    asegurar_ganancia(S, q, precio, atr)
    return q["stop"]


class Sleeve:
    """Una estrategia en un activo, con su propio capital (compone sus ganancias)."""

    def __init__(self, strat, risk, lev, fee, slip, equity, position=None, pending=None, activa=True,
                 simular_stops=True):
        self.S = STRATS[strat]; self.risk, self.lev, self.fee, self.slip = risk, lev, fee, slip
        self.activa = activa  # inactiva: no abre nuevas posiciones, pero sigue manejando la que tenga abierta
        self.simular_stops = simular_stops  # en vivo el stop está puesto en Binance
        self.equity, self.pos, self.pending = equity, position, pending
        self.closed = []  # operaciones cerradas en este paso
        self.comisiones, self.ordenes = 0.0, 0  # pagadas en este paso (para las estadísticas de la app)

    def _in(self, px, side):
        return px * (1 + self.slip) if side == "long" else px * (1 - self.slip)

    def _out(self, px, side):
        return px * (1 - self.slip) if side == "long" else px * (1 + self.slip)

    def open(self, side, px, atr, t):
        e, dist = self._in(px, side), self.S["stop_atr"] * atr
        if not dist > 0:
            return
        q = min(self.equity * self.risk / dist, self.equity * self.lev / e)
        self.equity -= q * e * self.fee
        self.comisiones += q * e * self.fee; self.ordenes += 1
        self.pos = dict(side=side, q=q, e=e, stop=e - dist if side == "long" else e + dist, bars=0, t=t, atr0=atr)

    def close(self, px, t, reason):
        p = self.pos
        x, sg = self._out(px, p["side"]), 1 if p["side"] == "long" else -1
        pnl = sg * (x - p["e"]) * p["q"] - p["q"] * x * self.fee
        self.comisiones += p["q"] * x * self.fee; self.ordenes += 1
        self.equity += pnl
        self.closed.append(dict(side=p["side"], entrada_t=p["t"], salida_t=t, entrada=p["e"], salida=x,
                                cantidad=p["q"], pnl=pnl, motivo=reason, capital=self.equity))
        self.pos = None

    def execute_pending(self, px, atr, t):
        a = self.pending
        if not a:
            return
        if self.pos and (a == "exit" or a != self.pos["side"]):
            self.close(px, t, "salida_señal" if a == "exit" else "reversa")
        if a in ("long", "short") and not self.pos:
            self.open(a, px, atr, t)
        self.pending = None

    def on_bar(self, D, i):
        """Procesa la vela i ya cerrada: ejecuta lo pendiente a su apertura, revisa stops, actualiza trailing y decide."""
        O, H, L, C, ATR, T = D["O"], D["H"], D["L"], D["C"], D["ATR"], D["T"]
        self.execute_pending(O[i], ATR[i - 1], T[i])
        p = self.pos
        if p and self.simular_stops and ((p["side"] == "long" and L[i] <= p["stop"]) or (p["side"] == "short" and H[i] >= p["stop"])):
            self.close(min(p["stop"], O[i]) if p["side"] == "long" else max(p["stop"], O[i]), T[i], "stop")
        p = self.pos
        if p:
            p["bars"] += 1
            if self.S["trail_atr"] > 0:
                d = self.S["trail_atr"] * ATR[i]
                p["stop"] = max(p["stop"], C[i] - d) if p["side"] == "long" else min(p["stop"], C[i] + d)
            asegurar_ganancia(self.S, p, C[i], ATR[i])
        sig = self.S["entry"](D, i) if self.activa else None
        mb = self.S.get("max_bars", 0)
        if sig and (not self.pos or self.pos["side"] != sig):
            self.pending = sig
        elif self.pos and (self.S["exit"](D, i, self.pos["side"]) or (mb and self.pos["bars"] >= mb)):
            self.pending = "exit"

    def mark(self, price):
        p = self.pos
        return self.equity + ((1 if p["side"] == "long" else -1) * (price - p["e"]) * p["q"] if p else 0.0)


# estrategias definidas como datos (carpetas estrategias/ y mis_estrategias/)
try:
    import catalogo as _catalogo
    _catalogo.cargar(STRATS, NOMBRES)
except Exception:  # un catálogo roto nunca debe frenar al bot
    pass
