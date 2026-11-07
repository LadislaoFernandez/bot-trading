"""Corazón del bot: estado, capital de cada parte, plan de estrategias y el modo simulado (sin órdenes reales).
La app (app.py) lo corre en un hilo; live.py usa estas mismas funciones para operar en Binance.
"""
import csv
import json
import os
import time
import traceback
from datetime import datetime, timezone

import config as K
from i18n import num, t
from data import exchange, fetch_recent
from engine import Sleeve, explain, prepare


def now_ms():
    return int(time.time() * 1000)


def fmt_t(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(K.LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_state():
    if os.path.exists(K.STATE_FILE):
        with open(K.STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
        _limpiar_quitadas(st)
        return st
    # estado nuevo: todo el capital empieza sin asignar y aplicar_asignacion lo reparte según los montos elegidos
    return {"inicio": datetime.now().isoformat(timespec="seconds"), "last_bar": {}, "modo": K.MODO,
            "capital_inicial": K.INITIAL_CAPITAL, "aportes": 0.0, "libre": K.INITIAL_CAPITAL, "aplicado": {},
            "activas": estrategias_activas(),
            "sleeves": {f"{a}_{s}": {"equity": 0.0, "pos": None, "pending": None} for a in K.SYMBOLS for s in NOMBRES}}


def _limpiar_quitadas(st):
    """Partes de estrategias que ya no existen (quitadas de mis estrategias): su capital vuelve a 'sin asignar'. Las que
    tienen una posición abierta u orden pendiente se dejan hasta que se resuelvan."""
    for k in list(st.get("sleeves", {})):
        s = k.split("_", 1)[1]
        v = st["sleeves"][k]
        if s not in NOMBRES and not v.get("pos") and not v.get("pending"):
            st["libre"] = st.get("libre", 0.0) + v.get("equity", 0.0)
            del st["sleeves"][k]
            st.get("aplicado", {}).pop(k, None)


def save_state(st):
    import archivos
    archivos.escribir_json(K.STATE_FILE, st, indent=2)


def append_csv(path, rows, fields):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerows(rows)


NOMBRES = __import__("engine").NOMBRES  # un solo registro de estrategias (engine + catálogo)


def nombre(s):
    import mercado
    return mercado.nombre_estrategia(s)


def lado(x):
    return t({"long": "compra", "short": "venta en corto"}[x])


def motivo(x):
    return t({"stop": "stop", "salida_señal": "señal de salida", "reversa": "cambio de dirección",
              "cierre_manual": "cierre manual", "sin_stop": "sin stop"}.get(x, x))


def leer_ajustes():
    try:
        with open("ajustes.json", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar_ajustes(**cambios):
    import archivos
    d = leer_ajustes(); d.update(cambios)
    archivos.escribir_json("ajustes.json", d, indent=2)


def estrategias_activas():
    a = leer_ajustes().get("activas")
    a = [x for x in a if x in NOMBRES and x not in K.RETIRADAS] if isinstance(a, list) else None
    return a or list(K.STRATEGIES)


def guardar_activas(activas):
    guardar_ajustes(activas=list(activas))


def auto_ajustes(aj=None):
    return (aj or leer_ajustes()).get("auto", {}) or {}


def modo_auto(aj=None):
    return bool(auto_ajustes(aj).get("activo"))


def montos_auto(modo=None):
    m = auto_ajustes().get("montos", {}).get(modo or K.MODO)
    return {a: float(v) for a, v in m.items()} if isinstance(m, dict) else None


def guardar_auto(activo=None, montos=None, modo=None):
    au = auto_ajustes()
    if activo is not None:
        au["activo"] = bool(activo)
    if montos is not None:
        au.setdefault("montos", {})[modo or K.MODO] = {a: round(float(v), 2) for a, v in montos.items()}
        au.setdefault("version_montos", {})[modo or K.MODO] = au.get("version_montos", {}).get(modo or K.MODO, 0) + 1
    guardar_ajustes(auto=au)


def plan(st, Ds, minimo=None):
    """Qué estrategias operan en cada moneda y con cuánto. En modo manual: las activadas, con los montos elegidos.
    Con el piloto automático: las estrategias base, con el capital repartido en partes iguales (ver auto.py)."""
    manual = estrategias_activas()
    if not modo_auto():
        st.pop("auto", None)
        return {a: list(manual) for a in K.SYMBOLS}, None
    import auto
    import mercado
    hist = mercado.cargar()  # sin historial todavía: usa las estrategias base y hace la revisión cuando esté listo
    return auto.plan(st, hist, minimo=minimo, log=log, reduccion=max(0.0, base_capital(st) - K.INITIAL_CAPITAL),
                     ahora=datetime.fromtimestamp(now_ms() / 1000))


def configurar_modo(modo):
    """Apunta el bot a los archivos, el capital y los parámetros de riesgo del modo elegido."""
    aj = leer_ajustes()
    K.MODO = modo
    for k, v in K.ARCHIVOS_MODO[modo].items():
        setattr(K, k, v)
    cap = aj.get("capital", {}).get(modo)
    K.INITIAL_CAPITAL = float(cap) if cap else 100.0
    r = aj.get("riesgo", {})
    K.RISK_PER_TRADE = float(r.get("por_operacion", 0.03))
    K.LIMITE_PERDIDA = float(r.get("limite_perdida", 0.25))
    K.ESPERA_ORDEN_LIMITE = int(r.get("espera_limite", 180))


def asignacion_actual():
    """Monto en USDT para cada parte (moneda_estrategia) del modo actual, o None si nunca se definió."""
    a = leer_ajustes().get("asignacion", {}).get(K.MODO)
    return {k: float(v) for k, v in a.items()} if isinstance(a, dict) else None


def guardar_asignacion(asig, modo=None):
    todas = leer_ajustes().get("asignacion", {})
    todas[modo or K.MODO] = {k: round(float(v), 2) for k, v in asig.items()}
    guardar_ajustes(asignacion=todas)


def asignacion_por_defecto(capital, activas):
    per = capital / (len(K.SYMBOLS) * max(1, len(activas)))
    return {f"{a}_{s}": per for a in K.SYMBOLS for s in activas}


def base_capital(st):
    return (st.get("capital_inicial") or K.INITIAL_CAPITAL) + st.get("aportes", 0.0)


def aplicar_capital(st):
    """Si cambiaste el capital del modo, la diferencia entra o sale del capital sin asignar (como un depósito o retiro)."""
    delta = K.INITIAL_CAPITAL - base_capital(st)
    if abs(delta) < 0.01:
        return
    if delta < 0 and -delta > st.get("libre", 0.0) + 1e-9:
        falta = -delta - st.get("libre", 0.0)
        if abs(st.get("capital_pendiente", 0) - K.INITIAL_CAPITAL) > 0.005:  # se anota una sola vez
            if modo_auto():
                log(t("El capital del modo baja a {c} USDT cuando se cierren las posiciones abiertas (faltan {f} USDT "
                      "sin asignar).", c=num(K.INITIAL_CAPITAL), f=num(falta)))
            else:
                log(t("El capital del modo quedó en {b} USDT y no en {c}: para bajarlo faltan {f} USDT sin asignar. Bajá "
                      "los montos de las estrategias (o las que tienen una posición abierta lo liberan al cerrarla).",
                      b=num(base_capital(st) - st.get("libre", 0.0)), c=num(K.INITIAL_CAPITAL), f=num(falta)))
        st["capital_pendiente"] = K.INITIAL_CAPITAL
        delta = -st.get("libre", 0.0)
    else:
        st.pop("capital_pendiente", None)
    if abs(delta) < 0.01:
        return
    st["libre"] = st.get("libre", 0.0) + delta
    st["aportes"] = st.get("aportes", 0.0) + delta
    if st.get("ref_limite"):
        st["ref_limite"] += delta
    log(t("Capital del modo ajustado en {d} USDT (ahora {b} USDT).", d=num(delta, 2, True), b=num(base_capital(st))))


def aplicar_asignacion(st, activas, asig_auto=None):
    """Lleva cada parte sin posición al monto elegido. Las que tienen posición abierta esperan a cerrarla.
    activas: lista de estrategias (todas las monedas) o diccionario moneda -> estrategias."""
    act = activas if isinstance(activas, dict) else {x: list(activas) for x in K.SYMBOLS}
    activas = sorted({s for v in act.values() for s in v}, key=list(NOMBRES).index)
    for a in K.SYMBOLS:
        for s in NOMBRES:
            st["sleeves"].setdefault(f"{a}_{s}", {"equity": 0.0, "pos": None, "pending": None})
    if "libre" not in st:  # estado de una versión anterior: se toma lo que hay tal como está
        st["libre"], st["aportes"] = 0.0, st.get("aportes", 0.0)
        st["aplicado"] = {k: v["equity"] for k, v in st["sleeves"].items() if v["equity"] > 0 or v["pos"]}
        if asignacion_actual() is None:
            guardar_asignacion({k: v for k, v in st["aplicado"].items() if k.split("_", 1)[1] in activas})
    asig = asig_auto if asig_auto is not None else asignacion_actual()
    if asig is None:
        asig = asignacion_por_defecto(base_capital(st), activas)
        guardar_asignacion(asig)
    aplicado = st.setdefault("aplicado", {})
    cambios, pendientes = [], []
    for k, v in st["sleeves"].items():
        if v["pos"]:
            continue
        ka, ks = k.split("_", 1)
        objetivo = asig.get(k, 0.0) if ks in act.get(ka, []) else 0.0
        if abs(objetivo - aplicado.get(k, 0.0)) < 0.005 and not (objetivo == 0 and v["equity"] > 1e-9):
            continue
        pendientes.append((objetivo - v["equity"], k, objetivo))
    # primero las que bajan (liberan capital) y después las que suben, para que no falte capital sin asignar
    for diff, k, objetivo in sorted(pendientes):
        v, meta = st["sleeves"][k], objetivo
        if diff > st["libre"] + 1e-9:  # no alcanza el capital sin asignar
            if asig_auto is None:  # con el piloto es normal: se empareja en el reequilibrio del día siguiente
                log(t("{k}: no alcanza el capital sin asignar para llevarla a {o} USDT; queda en {e} USDT.",
                      k=k, o=num(objetivo), e=num(v["equity"] + st["libre"])))
            diff = st["libre"]
            objetivo = v["equity"] + diff
        st["libre"] -= diff
        v["equity"] = objetivo
        v["pending"] = None if objetivo == 0 else v["pending"]
        aplicado[k] = meta if abs(objetivo - meta) < 0.005 else objetivo  # si quedó corta, se reintenta en la próxima
        cambios.append(f"{k} {num(objetivo)}")
    if abs(st["libre"]) < 1e-9:
        st["libre"] = 0.0
    if cambios:
        log(t("Montos aplicados: {c}. Sin asignar: {l} USDT.", c=", ".join(cambios), l=num(st["libre"])))
    st["activas"] = list(activas)
    if "auto" in st:
        st["auto"]["ref"] = {k: v["equity"] for k, v in st["sleeves"].items()}
    st["efectivo"] = {"activas": act, "asignacion": {k: (asig.get(k, 0.0) if k.split("_", 1)[1] in act.get(k.split("_", 1)[0], [])
                                                          else 0.0) for k in st["sleeves"]}}


def sumar_ordenes(st, d):
    """Estadísticas de órdenes para la app: cantidad, cuántas se completaron a mercado y comisiones pagadas."""
    o = st.setdefault("ordenes", dict(ordenes=0, mercado=0, comision=0.0, volumen=0.0, desde=now_ms()))
    for k in ("ordenes", "mercado", "comision", "volumen"):
        o[k] = o.get(k, 0) + d.get(k, 0)


def repartir_capital(st, activas):  # compatibilidad con versiones anteriores
    aplicar_capital(st)
    aplicar_asignacion(st, activas)


def _pr(v):
    return num(v, 2 if abs(v) >= 100 else 3 if abs(v) >= 1 else 5)


def _minus(txt):
    return txt[0].lower() + txt[1:] if len(txt) > 1 and txt[1].islower() else txt


def describir(asset, s, cond, sl, abrio, antes, activa, extra=None):
    """Arma el registro de una decisión: qué hizo la parte asset_s en esta revisión y por qué."""
    partes, accion = [], None
    for tr in sl.closed:
        partes.append(t("cerró la {l} por {m} ({p} USDT)", l=lado(tr["side"]), m=motivo(tr["motivo"]), p=num(tr["pnl"], 2, True)))
        accion = "cierra"
    if extra:
        partes += extra["partes"]
        accion = extra.get("accion") or accion
    if abrio:
        accion = "abre"
        partes.append(t("abrió {l} a {e} con stop en {s}", l=lado(abrio["side"]), e=_pr(abrio["e"]), s=_pr(abrio["stop"])))
    elif sl.pos and accion is None:
        accion = "mantiene"
        p = sl.pos
        txt = t("mantiene la {l} (entrada {e}, stop {s}", l=lado(p["side"]), e=_pr(p["e"]), s=_pr(p["stop"]))
        if antes and abs(antes["stop"] - p["stop"]) > 1e-12:
            txt += t(", el stop se movió desde {s}", s=_pr(antes["stop"]))
        partes.append(txt + ")")
    elif accion is None:
        accion = "no_abre" if activa else "inactiva"
        faltan = [_minus(c) for c, ok in cond if not ok]
        cumplen = sum(1 for _, ok in cond if ok)
        partes.append(t("no abre: se cumplen {c} de {n} condiciones", c=cumplen, n=len(cond)) if faltan else t("no abre"))
    if not activa:
        partes.append(t("estrategia desactivada: solo maneja la posición que ya tenía"))
    return dict(activo=asset, clave=s, estrategia=nombre(s), accion=accion, texto="; ".join(partes),
                condiciones=[[c, bool(ok)] for c, ok in cond])


def step(ex, st):
    velas = {}
    for asset, sym in K.SYMBOLS.items():
        rows = fetch_recent(ex, sym, K.TIMEFRAME, 1500)
        closed = [r for r in rows if r[0] + K.BAR_MS <= now_ms()]
        forming = rows[-1] if rows[-1][0] + K.BAR_MS > now_ms() else None
        velas[asset] = (forming, prepare(closed, K.BAR_MS, K.HTF_MS))
    aplicar_capital(st)
    act, asig = plan(st, {a: v[1] for a, v in velas.items()})
    aplicar_asignacion(st, act, asig)
    aplicar_capital(st)  # si se bajaron montos para bajar el capital, recién ahora hay sin asignar para sacarlo
    prices, total, items, vela_txt = {}, 0.0, [], None
    for asset, sym in K.SYMBOLS.items():
        forming, D = velas[asset]
        last_done = st["last_bar"].get(asset)
        new_idx = [i for i in range(1, D["n"]) if last_done is None or D["T"][i] > last_done]
        if last_done is None:
            new_idx = new_idx[-1:]  # primera vez: arranca desde la última vela cerrada
        prices[asset] = forming[1] if forming else D["C"][-1]
        if new_idx:
            t0 = D["T"][new_idx[-1]] / 1000
            vela_txt = t("{a} a {b}", a=f"{datetime.fromtimestamp(t0):%H:%M}", b=f"{datetime.fromtimestamp(t0 + 3600):%H:%M}")

        for s in NOMBRES:
            key = f"{asset}_{s}"
            ss = st["sleeves"][key]
            activa = s in act[asset]
            if not ss["pos"] and (not activa or ss["equity"] <= 1e-9):
                continue  # estrategia inactiva o sin monto asignado en esta moneda
            sl = Sleeve(s, K.RISK_PER_TRADE, K.MAX_LEVERAGE, K.FEE, K.SLIPPAGE, ss["equity"], ss["pos"], ss["pending"],
                        activa=activa)
            antes = dict(ss["pos"]) if ss["pos"] else None
            for i in new_idx:
                sl.on_bar(D, i)
            abrio = None
            if sl.pending and forming:  # la orden se coloca ya, a la apertura de la vela en curso
                before = sl.pos["side"] if sl.pos else None
                sl.execute_pending(forming[1], D["ATR"][-1], forming[0])
                now = sl.pos["side"] if sl.pos else None
                if now and now != before:
                    abrio = sl.pos
            for tr in sl.closed:
                trc = dict(tr, posicion=key, entrada_t=fmt_t(tr["entrada_t"]), salida_t=fmt_t(tr["salida_t"]))
                append_csv(K.TRADES_FILE, [trc], ["posicion", "side", "entrada_t", "salida_t", "entrada", "salida", "cantidad", "pnl", "motivo", "capital"])

            if new_idx:  # explicación de la decisión en la última vela cerrada
                items.append(describir(asset, s, explain(D, new_idx[-1], s) if activa else [], sl, abrio, antes, activa))
            ss.update(equity=sl.equity, pos=sl.pos, pending=sl.pending)
            sumar_ordenes(st, dict(ordenes=sl.ordenes, comision=sl.comisiones))
            total += sl.mark(prices[asset])
        if new_idx:
            st["last_bar"][asset] = D["T"][new_idx[-1]]

    # capital de partes sin posición que no se procesaron, y capital sin asignar
    for k, v in st["sleeves"].items():
        ka, ks = k.split("_", 1)
        if ka in act and not v["pos"] and (ks not in act[ka] or v["equity"] <= 1e-9):
            total += v["equity"]
    total += st.get("libre", 0.0)
    save_state(st)
    if items:
        log(t("Revisión de la vela de {v}:", v=vela_txt))
        for it in items:
            log(f"   {it['activo']} {it['estrategia']}: {it['texto']}.")
        with open(K.DECISIONES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"hora": datetime.now().isoformat(timespec="seconds"), "vela": vela_txt,
                                "items": items}, ensure_ascii=False) + "\n")
    else:
        log(t("Sin velas nuevas desde la última revisión: no hay nada que decidir."))
    append_csv(K.EQUITY_FILE, [{"hora": datetime.now().strftime("%Y-%m-%d %H:%M"), "total": round(total, 2),
                                "base": round(base_capital(st), 2)}], ["hora", "total", "base"])
    return total, prices


def show(st, prices=None, total=None):
    print("\n" + "=" * 72)
    print(f" Bot v2 (PAPER) | inicio {st['inicio']} | capital inicial {K.INITIAL_CAPITAL:.2f} USDT")
    for key, ss in st["sleeves"].items():
        p = ss["pos"]
        if p:
            pr = prices.get(key.split("_")[0]) if prices else None
            unreal = ((1 if p["side"] == "long" else -1) * (pr - p["e"]) * p["q"]) if pr else 0
            desc = f"{p['side'].upper():5} entrada {p['e']:.2f} stop {p['stop']:.2f} PnL abierto {unreal:+.2f}"
        else:
            desc = "sin posición"
        print(f"  {key:<13} capital {ss['equity']:7.2f} | {desc}")
    if total is not None:
        print(f" TOTAL (con posiciones abiertas): {total:.2f} USDT ({(total / K.INITIAL_CAPITAL - 1) * 100:+.2f}%)")
    print("=" * 72, flush=True)


# Estado del bot para la aplicación (lo lee la interfaz)
STATUS = {"estado": "detenido", "inicio": None, "ultima_revision": None, "proxima_revision": None, "ultimo_error": None}


def run_loop(st, stop_event=None, on_update=None, wake_event=None, paso=None, cliente=None):
    """Loop principal. stop_event detiene el bot; wake_event fuerza una revisión inmediata.
    paso/cliente: en modo demo o real, la función de un paso en vivo y la conexión a Binance."""
    import threading
    stop_event = stop_event or threading.Event()
    wake_event = wake_event or threading.Event()
    ex = cliente or exchange()
    paso = paso or step
    STATUS.update(estado="corriendo", inicio=time.time(), ultimo_error=None)
    log(t("Bot de trading {v} iniciado en modo {m}", v=getattr(K, "VERSION", ""), m=t(K.NOMBRE_MODO[K.MODO]).lower()) +
        (t(" (sin órdenes reales).") if K.MODO == "simulado" else t(" (órdenes en Binance).")))
    while not stop_event.is_set():
        ok = True
        STATUS["estado"] = "revisando"
        try:
            total, prices = paso(ex, st)
            show(st, prices, total)
            STATUS.update(ultima_revision=time.time(), ultimo_error=None)
            if on_update:
                on_update(st, prices, total)
        except Exception as e:
            ok = False
            STATUS["ultimo_error"] = f"{type(e).__name__}: {e}"[:300]
            log(t("Error (se reintenta en 1 minuto):") + "\n" + traceback.format_exc(limit=2))
        wait = K.BAR_MS / 1000 - (time.time() % (K.BAR_MS / 1000)) + 20  # 20 s después del cierre de cada vela de 1h
        if not ok:
            wait = min(wait, 60)  # p. ej. sin internet al prender la PC
        STATUS.update(estado="corriendo" if ok else "error", proxima_revision=time.time() + wait)
        log(t("Próxima revisión en {m} min.", m=f"{wait / 60:.0f}"))
        wake_event.clear()
        deadline = time.time() + wait
        while not stop_event.is_set() and not wake_event.is_set() and time.time() < deadline:
            stop_event.wait(min(1.0, max(0.0, deadline - time.time())))
        if wake_event.is_set() and not stop_event.is_set():
            log(t("Revisión manual pedida desde la aplicación."))
    STATUS.update(estado="detenido", proxima_revision=None)
    log(t("Bot detenido."))
