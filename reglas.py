"""Estrategias definidas como datos (JSON), sin código.

Una estrategia es un diccionario con sus reglas de entrada y salida escritas para la COMPRA; las de venta en corto se
arman solas, en espejo (por encima ↔ por debajo, máximo ↔ mínimo, RSI 30 ↔ 70, etc.). Ejemplo (RSI(2)):

    {"id": "RSI2_DATOS", "nombre": "RSI(2)", "direccion": "ambas",
     "entrada": [{"a": "C", "op": ">", "b": "EMA200"}, {"a": "RSI2", "op": "<", "b": 10}],
     "salida":  [{"a": "C", "op": ">", "b": "SMA5"}],
     "stop_atr": 3, "trail_atr": 0, "max_velas": 20}

Condiciones:
  {"a": serie, "op": ">" | "<" | ">=" | "<=" | "cruza_arriba" | "cruza_abajo", "b": serie o número, "b_desfase": n}
  {"a": serie, "op": "gira_arriba" | "gira_abajo"}            la serie da la vuelta en esta vela
  {"a": serie, "op": "sube" | "cae", "n": velas, "desfase": d}  a[i-d] comparado con a[i-d-n]
  {"op": "squeeze", "n": velas}                               hubo squeeze en las últimas n velas
Todas las condiciones de "entrada" tienen que cumplirse a la vez; lo mismo las de "salida" (vacía = sale solo por stop
o por tiempo). Solo se usan series ya calculadas en velas cerradas, así que no hay forma de mirar el futuro.
"""
import math

SERIES = {  # serie -> (nombre para mostrar, espejo para ventas en corto, tipo de umbral)
    "C": ("Precio de cierre", "C", "precio"), "O": ("Apertura", "O", "precio"),
    "EMA20": ("EMA 20", "EMA20", "precio"), "EMA50": ("EMA 50", "EMA50", "precio"),
    "EMA200": ("EMA 200", "EMA200", "precio"), "SMA20": ("Media de 20", "SMA20", "precio"),
    "SMA5": ("Media de 5", "SMA5", "precio"),
    "BBU": ("Banda superior de Bollinger", "BBL", "precio"), "BBL": ("Banda inferior de Bollinger", "BBU", "precio"),
    "DH48": ("Máximo de 48 h", "DL48", "precio"), "DL48": ("Mínimo de 48 h", "DH48", "precio"),
    "RSI14": ("RSI", "RSI14", "oscilador"), "RSI2": ("RSI(2)", "RSI2", "oscilador"),
    "ADX": ("ADX", "ADX", "neutro"), "ATR": ("ATR", "ATR", "neutro"),
    "V": ("Momentum", "V", "cero"), "ST": ("Supertrend", "ST", "cero"), "trend": ("Tendencia de 4 h", "trend", "cero"),
}
OPS = {">", "<", ">=", "<=", "cruza_arriba", "cruza_abajo", "gira_arriba", "gira_abajo", "sube", "cae", "squeeze"}
ESPEJO_OP = {">": "<", "<": ">", ">=": "<=", "<=": ">=", "cruza_arriba": "cruza_abajo", "cruza_abajo": "cruza_arriba",
             "gira_arriba": "gira_abajo", "gira_abajo": "gira_arriba", "sube": "cae", "cae": "sube", "squeeze": "squeeze"}


def _nan(v):
    return v is None or (isinstance(v, float) and math.isnan(v))


def completar(D):
    """Agrega a las velas preparadas las series derivadas que usan las reglas."""
    if "BBU" not in D:
        D["BBU"] = [m + 2 * s for m, s in zip(D["SMA20"], D["SD20"])]
        D["BBL"] = [m - 2 * s for m, s in zip(D["SMA20"], D["SD20"])]
    return D


def espejo(c):
    """La misma condición, para ventas en corto."""
    c = dict(c)
    neutro = SERIES.get(c.get("a"), ("", "", "neutro"))[2] == "neutro"
    if c.get("op") in ("sube", "cae", "gira_arriba", "gira_abajo") and neutro:
        return c  # que el ADX caiga significa lo mismo comprando o vendiendo
    if c.get("op") in (">", "<", ">=", "<=", "cruza_arriba", "cruza_abajo") and neutro and not isinstance(c.get("b"), str):
        return c  # "ADX > 25" no tiene dirección
    if "a" in c:
        c["a"] = SERIES[c["a"]][1]
    c["op"] = ESPEJO_OP[c["op"]]
    b = c.get("b")
    if isinstance(b, str):
        c["b"] = SERIES[b][1]
    elif b is not None:
        tipo = SERIES[c["a"]][2]
        c["b"] = 100 - b if tipo == "oscilador" else -b if tipo == "cero" else b
    return c


def _valor(D, x, i):
    return D[x][i] if isinstance(x, str) else float(x)


def cumple(D, c, i):
    op = c["op"]
    if op == "squeeze":
        n = int(c.get("n", 6))
        return any(D["sqz"][q] for q in range(max(0, i - n), i + 1))
    a = D[c["a"]]
    if op in ("gira_arriba", "gira_abajo"):
        if i < 2:
            return False
        v0, v1, v2 = a[i], a[i - 1], a[i - 2]
        if op == "gira_arriba":
            return _gt(v0, v1) and not _gt(v1, v2)
        return _lt(v0, v1) and not _lt(v1, v2)
    if op in ("sube", "cae"):
        n, d = int(c.get("n", 1)), int(c.get("desfase", 0))
        if i - d - n < 0:
            return False
        dif = a[i - d] - a[i - d - n]
        return (dif > 0) if op == "sube" else (dif < 0)
    bd = int(c.get("b_desfase", 0))
    if i - bd < 1:
        return False
    va = a[i]
    vb = _valor(D, c["b"], i - bd)
    if op == ">":
        return _gt(va, vb)
    if op == "<":
        return _lt(va, vb)
    if op == ">=":
        return not _nan(va) and not _nan(vb) and va >= vb
    if op == "<=":
        return not _nan(va) and not _nan(vb) and va <= vb
    pa, pb = a[i - 1], _valor(D, c["b"], i - 1 - bd)
    if op == "cruza_arriba":
        return _gt(va, vb) and not _nan(pa) and not _nan(pb) and pa <= pb
    if op == "cruza_abajo":
        return _lt(va, vb) and not _nan(pa) and not _nan(pb) and pa >= pb
    return False


def _gt(a, b):
    return not _nan(a) and not _nan(b) and a > b


def _lt(a, b):
    return not _nan(a) and not _nan(b) and a < b


def validar(d):
    """Controla que una definición sea correcta. Devuelve la lista de problemas (vacía si está bien)."""
    p = []
    if not isinstance(d, dict):
        return ["no es un diccionario"]
    if not isinstance(d.get("id"), str) or not d["id"].replace("_", "").isalnum() or len(d["id"]) > 40:
        p.append("id inválido")
    if d.get("direccion", "ambas") not in ("ambas", "largo", "corto"):
        p.append("direccion inválida")
    for k in ("entrada", "salida"):
        cs = d.get(k, [])
        if not isinstance(cs, list) or (k == "entrada" and not cs) or len(cs) > 6:
            p.append(f"{k} inválida")
            continue
        for c in cs:
            if not isinstance(c, dict) or c.get("op") not in OPS:
                p.append(f"{k}: operación inválida"); continue
            if c["op"] != "squeeze" and c.get("a") not in SERIES:
                p.append(f"{k}: serie inválida {c.get('a')}")
            b = c.get("b")
            if c["op"] in (">", "<", ">=", "<=", "cruza_arriba", "cruza_abajo"):
                if not (b in SERIES or (isinstance(b, (int, float)) and not isinstance(b, bool) and math.isfinite(b))):
                    p.append(f"{k}: comparación inválida")
            for nk in ("n", "desfase", "b_desfase"):
                if nk in c and not (isinstance(c[nk], int) and 0 <= c[nk] <= 48):
                    p.append(f"{k}: {nk} inválido")
    for k, lo, hi in (("stop_atr", 0.5, 6), ("trail_atr", 0, 8), ("max_velas", 0, 200), ("be_atr", 0, 10)):
        v = d.get(k, 0)
        if not isinstance(v, (int, float)) or not lo <= v <= hi:
            p.append(f"{k} fuera de rango")
    return p


def compilar(d):
    """Convierte una definición en las funciones que usa el motor (mismo formato que STRATS)."""
    entrada, salida = list(d["entrada"]), list(d.get("salida", []))
    entrada_c, salida_c = [espejo(c) for c in entrada], [espejo(c) for c in salida]
    direc, min_velas = d.get("direccion", "ambas"), int(d.get("min_velas", 200))

    def entry(D, i):
        if i < min_velas:
            return None
        if direc in ("ambas", "largo") and all(cumple(D, c, i) for c in entrada):
            return "long"
        if direc in ("ambas", "corto") and all(cumple(D, c, i) for c in entrada_c):
            return "short"
        return None

    def exit_(D, i, side):
        cs = salida if side == "long" else salida_c
        return bool(cs) and all(cumple(D, c, i) for c in cs)

    return dict(entry=entry, exit=exit_, stop_atr=float(d.get("stop_atr", 2)), trail_atr=float(d.get("trail_atr", 0)),
                max_bars=int(d.get("max_velas", 0)), be_atr=float(d.get("be_atr", 0)), datos=d)


# ------------------------------------------------------------------ textos
OP_TXT = {">": "{a} por encima de {b}", "<": "{a} por debajo de {b}", ">=": "{a} igual o por encima de {b}",
          "<=": "{a} igual o por debajo de {b}", "cruza_arriba": "{a} cruza por encima de {b}",
          "cruza_abajo": "{a} cruza por debajo de {b}", "gira_arriba": "{a} gira hacia arriba",
          "gira_abajo": "{a} gira hacia abajo", "sube": "{a} subiendo en las últimas {n} velas",
          "cae": "{a} cayendo en las últimas {n} velas", "squeeze": "Squeeze en las últimas {n} velas"}


def texto(c, D=None, i=None):
    """Descripción de una condición, con los valores actuales si se pasan las velas."""
    from i18n import num, t
    nombre = lambda s: t(SERIES[s][0]) if isinstance(s, str) else num(s, 0 if float(s).is_integer() else 2)
    a = nombre(c["a"]) if "a" in c else ""
    b = nombre(c["b"]) if "b" in c else ""
    if D is not None and i is not None and c["op"] not in ("squeeze", "gira_arriba", "gira_abajo", "sube", "cae"):
        from engine import _f
        a += f" ({_f(D[c['a']][i])})"
        if isinstance(c.get("b"), str):
            b += f" ({_f(D[c['b']][i - int(c.get('b_desfase', 0))])})"
    if c.get("b_desfase"):
        b += " " + t("de la vela anterior")
    return t(OP_TXT[c["op"]], a=a, b=b, n=c.get("n", 6))


def explicar(d, D, i):
    """Condiciones de entrada en la vela i para la dirección que está más cerca de cumplirse."""
    completar(D)
    entrada = list(d["entrada"])
    opciones = []
    if d.get("direccion", "ambas") in ("ambas", "largo"):
        opciones.append(entrada)
    if d.get("direccion", "ambas") in ("ambas", "corto"):
        opciones.append([espejo(c) for c in entrada])
    mejor = max(opciones, key=lambda cs: sum(cumple(D, c, i) for c in cs))
    return [(texto(c, D, i), cumple(D, c, i)) for c in mejor]


def describir(d):
    """Resumen en una línea de cómo opera (para la tarjeta de la estrategia)."""
    from i18n import num, t
    dir_txt = {"ambas": t("Compra y vende en corto"), "largo": t("Solo compras"), "corto": t("Solo ventas en corto")}
    partes = [dir_txt[d.get("direccion", "ambas")] + ". " + t("Entra cuando:") + " " +
              "; ".join(texto(c) for c in d["entrada"]) + "."]
    if d.get("salida"):
        partes.append(t("Sale cuando:") + " " + "; ".join(texto(c) for c in d["salida"]) + ".")
    stop = t("Stop a {s} ATR", s=num(d.get("stop_atr", 2), 1))
    if d.get("trail_atr"):
        stop += " " + t("que sigue al precio a {x} ATR", x=num(d["trail_atr"], 1))
    if d.get("be_atr"):
        stop += ", " + t("que pasa a la entrada con {x} ATR de ganancia", x=num(d["be_atr"], 1))
    if d.get("max_velas"):
        stop += ", " + t("o sale a las {n} horas", n=d["max_velas"])
    partes.append(stop + ".")
    return " ".join(partes)
