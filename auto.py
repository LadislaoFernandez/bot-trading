"""Piloto automático: el bot administra solo la cartera, como si vos usaras la app.

Cómo funciona (lo que mejor resultado dio en las simulaciones de 2023 a 2026 con el código del bot):
  1. Usa las estrategias base (Breakout y Resorte de tendencia) en BTC, ETH y SOL, prendidas todo el tiempo. No las
     prende ni apaga según el tipo de mercado: eso hacía perder las operaciones grandes, que son las que dan la ganancia.
  2. Reequilibra una vez por día: reparte todo el capital (el del modo más lo ganado) en partes iguales entre las
     partes en uso. Una parte con una posición abierta toma su monto nuevo cuando la cierra. Si a una parte no le
     alcanza para el mínimo por orden de Binance, se deja afuera y su dinero va a las demás.
  3. Revisión mensual de seguridad: una estrategia califica si ganó plata en los últimos 12 meses, y solo se juzga con
     al menos 2 años de historial (mercado.califica). Si una estrategia en uso falla la revisión 3 meses seguidos, deja
     de recibir dinero; si una que estaba afuera pasa 3 meses seguidos, vuelve. Cada cambio queda en Avisos.
     En las simulaciones de 2023 a 2026 nunca sacó a Breakout ni a Resorte, y habría sacado a Reversión y a RSI(2) en
     marzo de 2024 (una regla más exigente sacaba estrategias buenas en un mal momento y perdía la recuperación).
Las posiciones abiertas de una estrategia que sale se siguen manejando hasta cerrarse.
"""
from datetime import datetime

import config as K
import mercado as M
from i18n import num, t

MESES_HISTERESIS = 3


def base():
    """Estrategias del piloto: Breakout y Resorte de tendencia, más las del laboratorio que terminaron su observación
    ganándoles (ajustes.json → piloto_extra)."""
    extra = []
    try:
        import paper_trader as PT
        extra = [s for s in PT.leer_ajustes().get("piloto_extra", []) or [] if s in M.PT_NOMBRES]
    except Exception:  # sin ajustes legibles: solo la base fija
        pass
    fija = [s for s in K.PILOTO_BASE if s in M.PT_NOMBRES]
    return fija + [s for s in extra if s not in fija]


def _avisar(id_, tipo, titulo, texto):
    try:
        import alertas
        alertas.agregar(id_, tipo, titulo, texto)
    except Exception:  # un aviso que no se pudo guardar nunca debe frenar al bot
        pass


def revisar(au, historial, ahora=None, log=None):
    """Revisión mensual. Se hace una vez por mes, la primera vez que el bot revisa en ese mes con el historial listo."""
    ahora = ahora or datetime.now()
    mes = ahora.strftime("%Y-%m")
    if au.get("mes") == mes or not historial:
        return False
    if not any("semestres" in (historial.get("estrategias", {}).get(s) or {}) for s in base()):
        return False  # historial de una versión anterior: espera a que se recalcule para hacer la revisión
    dentro = set(au.get("dentro") if au.get("dentro") is not None else base())
    racha, resultado = au.setdefault("racha", {}), {}
    for s in base():
        ok, sem = M.califica(historial, s)
        resultado[s] = {"califica": ok, "semestres": [round(x, 2) for x in sem]}
        if ok is None:  # sin datos suficientes: no cuenta ni a favor ni en contra
            continue
        esta = s in dentro
        falla = (not ok) if esta else ok  # en uso y falla, o afuera y pasa
        racha[s] = racha.get(s, 0) + 1 if falla else 0
        nombre = M.nombre_estrategia(s)
        if esta and falla:
            if racha[s] >= MESES_HISTERESIS:
                dentro.discard(s); racha[s] = 0
                _avisar(f"piloto_sale_{s}_{mes}", "empeora", t("{e} deja de recibir dinero", e=nombre), t(
                    "Perdió plata en los últimos 12 meses en {n} revisiones mensuales seguidas. El piloto deja de darle "
                    "dinero; sus posiciones abiertas se manejan hasta cerrarse. Vuelve sola si pasa la revisión {n} meses "
                    "seguidos.", n=MESES_HISTERESIS))
            else:
                _avisar(f"piloto_falla_{s}_{mes}", "empeora", t("{e} falló la revisión mensual", e=nombre), t(
                    "Perdió plata en los últimos 12 meses ({p}). Falló {r} de {n} revisiones seguidas: si falla {n} "
                    "seguidas, el piloto le deja de dar dinero. Por ahora sigue igual.", p=num(M.ultimo_anio(sem), 1, True) + " %",
                    r=racha[s], n=MESES_HISTERESIS))
        elif not esta and falla:
            if racha[s] >= MESES_HISTERESIS:
                dentro.add(s); racha[s] = 0
                _avisar(f"piloto_vuelve_{s}_{mes}", "recupera", t("{e} vuelve al piloto", e=nombre), t(
                    "Pasó la revisión mensual {n} meses seguidos: desde hoy vuelve a recibir dinero.", n=MESES_HISTERESIS))
    if not dentro:
        _avisar(f"piloto_vacio_{mes}", "empeora", t("El piloto no tiene estrategias en uso"), t(
            "Ninguna estrategia base pasa la revisión mensual: todo el capital queda sin asignar hasta que alguna vuelva."))
    au.update(mes=mes, dentro=sorted(dentro, key=base().index), revision=resultado, revision_hora=ahora.timestamp())
    if log:
        log(t("Piloto automático: revisión mensual hecha. En uso: {e}.",
              e=", ".join(M.nombre_estrategia(s) for s in au["dentro"]) or t("ninguna")))
    return True


def repartir(total, partes, minimo=None):
    """Partes iguales. La parte que no llega al mínimo de Binance sale (primero la que más necesita) y su dinero va a las
    demás. Devuelve ({'BTC_TL': monto}, [partes que quedaron afuera por el mínimo])."""
    partes, afuera = list(partes), []
    while partes:
        m = total / len(partes)
        bajas = [k for k in partes if minimo and (minimo(k.split("_", 1)[1], k.split("_", 1)[0]) or 0) > m]
        if not bajas:
            return {k: int(m * 100) / 100 for k in partes}, afuera
        k = max(bajas, key=lambda k: minimo(k.split("_", 1)[1], k.split("_", 1)[0]))
        partes.remove(k); afuera.append(k)
    return {}, afuera


def plan(st, historial, minimo=None, log=None, reduccion=0.0, ahora=None):
    """Estrategias por moneda y monto de cada parte. Reequilibra una vez por día (o si cambió la cartera o el capital)."""
    ahora = ahora or datetime.now()
    au = st.get("auto") or {}
    if "dentro" not in au:  # estado del piloto anterior (por tipo de mercado): empieza de nuevo
        au = {"dentro": None, "racha": {}}
    st["auto"] = au
    b = base()
    if au.get("dentro") is not None:  # una estrategia que entra al piloto (del laboratorio) empieza en uso
        nuevas = [s for s in b if s not in (au.get("conocidas") or K.PILOTO_BASE)]
        au["dentro"] = [s for s in au["dentro"] if s in b] + [s for s in nuevas if s not in au["dentro"]]
    au["conocidas"] = b
    revisado = revisar(au, historial, ahora, log)
    dentro = au.get("dentro") if au.get("dentro") is not None else base()
    total = max(0.0, sum(v["equity"] for v in st["sleeves"].values()) + st.get("libre", 0.0) - reduccion)
    firma = [ahora.strftime("%Y-%m-%d"), list(dentro), round(reduccion, 2),
             round((st.get("capital_inicial") or 0) + st.get("aportes", 0.0), 2)]
    if au.get("firma") != firma or revisado or not au.get("asig") and dentro:
        partes = [f"{a}_{s}" for a in K.SYMBOLS for s in dentro]
        asig, afuera = repartir(total, partes, minimo)
        au.update(firma=firma, asig=asig, afuera=afuera, reequilibrio_hora=ahora.timestamp(), total=round(total, 2))
        if log:
            txt = (t("Piloto automático: reequilibrio diario, {d} en {n} partes de {m} cada una.", d=num(total),
                     n=len(asig), m=num(next(iter(asig.values())))) if asig else
                   t("Piloto automático: todo el capital queda sin asignar."))
            if afuera:
                txt += " " + t("Sin monto por el mínimo de Binance: {p}.", p=", ".join(afuera))
            log(txt)
    asig = au.get("asig") or {}
    act = {a: [s for s in dentro if f"{a}_{s}" in asig] for a in K.SYMBOLS}
    return act, dict(asig)


def proximo_reequilibrio(au):
    from datetime import timedelta
    h = (au or {}).get("reequilibrio_hora")
    return (datetime.fromtimestamp(h).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)) if h else None


def proxima_revision(au):
    hoy = datetime.now()
    return datetime(hoy.year + (hoy.month == 12), hoy.month % 12 + 1, 1)
