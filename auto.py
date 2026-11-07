"""Modo automático: el bot elige qué estrategias usar en cada moneda según el tipo de mercado.

En cada revisión, para cada moneda:
  1. Lee el tipo de mercado (tendencia alcista, bajista o lateral) en las últimas 3 velas cerradas de 1 hora.
     Solo cambia de tipo si las 3 coinciden, para no saltar de estrategia por un movimiento de una sola vela.
  2. Elige hasta 2 estrategias que en ese tipo de mercado ganaron al menos 1,10 veces lo que perdieron, con 30
     operaciones o más en el historial (las mismas reglas de la recomendación de la pantalla Estrategias), y que no
     vengan empeorando: si en los últimos 90 días perdió más de lo que ganó, no la usa hasta que se recupere.
  3. Reparte todo el capital del bot (el del modo más lo ganado en operaciones cerradas) en partes iguales entre las
     estrategias elegidas en las tres monedas, así las ganancias se reinvierten.
Si en una moneda no conviene ninguna estrategia, no abre operaciones nuevas y su parte va a las otras monedas.
Las posiciones abiertas de una estrategia que deja de estar elegida se siguen manejando hasta cerrarse.
"""
import config as K
import mercado as M
from i18n import num, t

MAX_POR_MONEDA = 2
VELAS_CONFIRMACION = 3


def regimen_estable(D, previo):
    n = D["n"]
    if n < VELAS_CONFIRMACION + 1:
        return previo
    rs = {M.regimen(D, i) for i in range(n - VELAS_CONFIRMACION, n)}
    actual = M.regimen(D, n - 1)
    return actual if len(rs) == 1 else (previo or actual)


def elegir(historial, regimen):
    return [f["estrategia"] for f in M.recomendar(historial, regimen) if f["recomendable"]][:MAX_POR_MONEDA]


def plan(st, Ds, historial, montos=None, log=None, reduccion=0.0):
    """Ds: velas preparadas de cada moneda. Devuelve (estrategias por moneda, monto de cada parte).

    Todo el capital del bot (el del modo más lo ganado o menos lo perdido en operaciones cerradas) se reparte en partes
    iguales entre las estrategias elegidas en todas las monedas. Si en una moneda no conviene ninguna, su parte va a
    las otras. Las partes con una posición abierta toman el monto nuevo cuando la cierran."""
    au = st.setdefault("auto", {"regimen": {}, "seleccion": {}})
    act, cambios = {}, []
    for a in K.SYMBOLS:
        D = Ds.get(a)
        reg = regimen_estable(D, au["regimen"].get(a)) if D else au["regimen"].get(a)
        sel = elegir(historial, reg) if reg else []
        act[a] = sel
        if au["seleccion"].get(a) != sel or au["regimen"].get(a) != reg:
            nombres = ", ".join(M.nombre_estrategia(s) for s in sel) if sel else t("ninguna (no abre operaciones nuevas)")
            cambios.append(t("{a} ({r}): {e}", a=a, r=t(reg).lower() if reg else "—", e=nombres))
        au["regimen"][a], au["seleccion"][a] = reg, sel
    partes = [f"{a}_{s}" for a, sel in act.items() for s in sel]
    # reduccion: si bajaste el capital del modo, esa parte se deja sin asignar para poder sacarla
    total = max(0.0, sum(v["equity"] for v in st["sleeves"].values()) + st.get("libre", 0.0) - reduccion)
    por = int(total / len(partes) * 100) / 100 if partes else 0.0
    asig = {k: por for k in partes}
    if cambios and log:
        log(t("Modo automático, estrategias elegidas:") + " " + "; ".join(cambios) + ". " +
            (t("Capital repartido: {x} USDT en cada una de las {n} partes.", x=num(por), n=len(partes)) if partes else
             t("Todo el capital queda sin asignar hasta que convenga alguna estrategia.")))
    return act, asig


def montos_por_defecto(asignacion, activas, capital):
    """Dinero por moneda al encender el modo automático: lo que ya tenía asignado cada moneda."""
    if asignacion:
        m = {a: sum(v for k, v in asignacion.items() if k.startswith(a + "_") and k.split("_", 1)[1] in activas)
             for a in K.SYMBOLS}
        if sum(m.values()) > 0:
            return {a: round(v, 2) for a, v in m.items()}
    return {a: int(capital / len(K.SYMBOLS) * 100) / 100 for a in K.SYMBOLS}


def describir_montos(montos):
    return ", ".join(f"{a} {num(v)} USDT" for a, v in montos.items())
