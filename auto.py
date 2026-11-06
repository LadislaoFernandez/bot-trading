"""Modo automático: el bot elige qué estrategias usar en cada moneda según el tipo de mercado.

En cada revisión, para cada moneda:
  1. Lee el tipo de mercado (tendencia alcista, bajista o lateral) en las últimas 3 velas cerradas de 1 hora.
     Solo cambia de tipo si las 3 coinciden, para no saltar de estrategia por un movimiento de una sola vela.
  2. Elige hasta 2 estrategias que en ese tipo de mercado ganaron al menos 1,10 veces lo que perdieron, con 30
     operaciones o más en el historial (las mismas reglas de la recomendación de la pantalla Estrategias), y que no
     vengan empeorando: si en los últimos 90 días perdió más de lo que ganó, no la usa hasta que se recupere.
  3. Reparte en partes iguales entre ellas el dinero de esa moneda: el monto que elegiste más lo ganado (o menos lo
     perdido) por las operaciones de esa moneda desde que lo elegiste, así las ganancias se reinvierten.
Si ninguna estrategia conviene, esa moneda no abre operaciones nuevas y su dinero queda sin asignar.
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


def plan(st, Ds, historial, montos, log=None):
    """Ds: velas preparadas de cada moneda. montos: USDT por moneda.
    Devuelve (estrategias por moneda, monto de cada parte)."""
    au = st.setdefault("auto", {"regimen": {}, "seleccion": {}})
    acum, ref = au.setdefault("resultado", {}), au.get("ref")
    if ref is not None:  # lo que cambió el capital de cada parte desde la revisión anterior = resultado de sus operaciones
        for k, v in st["sleeves"].items():
            a = k.split("_", 1)[0]
            acum[a] = acum.get(a, 0.0) + v["equity"] - ref.get(k, v["equity"])
    act, asig, cambios = {}, {}, []
    for a in K.SYMBOLS:
        D = Ds.get(a)
        reg = regimen_estable(D, au["regimen"].get(a)) if D else au["regimen"].get(a)
        sel = elegir(historial, reg) if reg else []
        act[a] = sel
        m = max(0.0, float(montos.get(a, 0.0)) + acum.get(a, 0.0)) if montos.get(a) else 0.0
        for s in sel:
            asig[f"{a}_{s}"] = int(m / len(sel) * 100) / 100
        if au["seleccion"].get(a) != sel or au["regimen"].get(a) != reg:
            nombres = ", ".join(M.nombre_estrategia(s) for s in sel) if sel else t("ninguna (no abre operaciones nuevas)")
            cambios.append(t("{a} ({r}): {e}", a=a, r=t(reg).lower() if reg else "—", e=nombres))
        au["regimen"][a], au["seleccion"][a] = reg, sel
    if cambios and log:
        log(t("Modo automático, estrategias elegidas:") + " " + "; ".join(cambios) + ".")
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
