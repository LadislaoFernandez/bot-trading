"""Operación en Binance Futuros (cuenta demo o real) con las mismas decisiones que el modo simulado.

Cómo ejecuta:
- Cuenta en modo cobertura (posiciones LONG y SHORT separadas por activo), margen aislado y apalancamiento máximo
  del bot. Así dos estrategias pueden tener posiciones opuestas en el mismo activo.
- Entradas y salidas por señal: orden límite "post-only" al mejor precio (comisión maker). Si no se llena en
  ESPERA_ORDEN_LIMITE segundos, completa lo que falte a mercado para no perder la señal.
- Cada posición tiene su stop puesto en Binance (se ejecuta aunque la PC esté apagada). El trailing se actualiza
  en cada revisión.
- Si una orden queda por debajo del mínimo de Binance, se saltea y queda anotado el motivo.
"""
import json
import time
from datetime import datetime

import config as K
import paper_trader as PT
from engine import Sleeve, explain, prepare
from i18n import num, t

LADO_POS = {"long": "LONG", "short": "SHORT"}


class Broker:
    def __init__(self, modo, api_key, secret):
        import ccxt
        self.ccxt = ccxt
        self.modo = modo
        self.stats = dict(ordenes=0, mercado=0, comision=0.0, volumen=0.0)  # órdenes del bot (se pasan al estado)
        self.ex = ccxt.binanceusdm({"apiKey": api_key, "secret": secret, "enableRateLimit": True,
                                    "options": {"adjustForTimeDifference": True}})
        if modo == "demo":
            if hasattr(self.ex, "enable_demo_trading"):
                self.ex.enable_demo_trading(True)
            else:
                self.ex.set_sandbox_mode(True)
        self.ex.load_markets()
        self.preparado = set()

    # ---------- cuenta
    def restricciones(self):
        """Permisos de la clave (solo cuenta real): futuros habilitados, retiros deshabilitados y restricción de IP."""
        f = getattr(self.ex, "sapi_get_account_apirestrictions", None) or getattr(self.ex, "sapiGetAccountApiRestrictions")
        r = f()
        return dict(futuros=bool(r.get("enableFutures")), retiros=bool(r.get("enableWithdrawals")),
                    ip=bool(r.get("ipRestrict")))

    def saldo(self):
        b = self.ex.fetch_balance()
        u = b.get("USDT", {})
        return dict(total=float(u.get("total") or 0), libre=float(u.get("free") or 0), usado=float(u.get("used") or 0))

    def preparar(self, symbols):
        """Modo cobertura, margen aislado y apalancamiento. Ignora los avisos de 'ya estaba así' y el rechazo por tener
        órdenes abiertas (-4067): pasa al reiniciar con posiciones abiertas, cuyos stops son órdenes, y la cuenta ya
        quedó configurada cuando se abrieron."""
        notas = []
        try:
            self.ex.set_position_mode(True)
        except Exception as e:
            if "No need" not in str(e) and "-4059" not in str(e) and "-4067" not in str(e):
                notas.append(f"Modo cobertura: {e}"[:160])
        for sym in symbols:
            if sym in self.preparado:
                continue
            for f, args in [(self.ex.set_margin_mode, ("isolated", sym)), (self.ex.set_leverage, (int(K.MAX_LEVERAGE), sym))]:
                try:
                    f(*args)
                except Exception as e:
                    if "No need" not in str(e) and "-4046" not in str(e) and "-4067" not in str(e):
                        notas.append(f"{sym}: {e}"[:160])
            self.preparado.add(sym)
        return notas

    def minimos(self, sym):
        m = self.ex.market(sym)
        lim = m.get("limits", {})
        return dict(costo=float((lim.get("cost") or {}).get("min") or 5.0),
                    cantidad=float((lim.get("amount") or {}).get("min") or 0.0))

    def redondear(self, sym, q):
        try:  # el pequeño margen evita que 0,0099999 se redondee hacia abajo a 0 por errores de coma flotante
            return float(self.ex.amount_to_precision(sym, q * (1 + 1e-9) + 1e-12)) if q > 0 else 0.0
        except Exception:
            return 0.0

    def precio_stop(self, sym, p):
        return float(self.ex.price_to_precision(sym, p))

    def libro(self, sym):
        ob = self.ex.fetch_order_book(sym, 5)
        return float(ob["bids"][0][0]), float(ob["asks"][0][0])

    def velas(self, sym, n=1500):
        return [r[:5] for r in self.ex.fetch_ohlcv(sym, K.TIMEFRAME, limit=n)]

    def posiciones(self, symbols):
        out = {}
        for p in self.ex.fetch_positions(symbols):
            lado = (p.get("side") or "").lower()
            c = abs(float(p.get("contracts") or 0))
            if c > 0 and lado in ("long", "short"):
                out[(p["symbol"], lado)] = out.get((p["symbol"], lado), 0.0) + c
        return out

    # ---------- órdenes
    def ejecutar(self, sym, side, qty, pos_side, log, espera=None, cierre=False):
        """Compra o vende qty con orden límite post-only y respaldo a mercado. Devuelve cantidad, precio medio, comisión.
        cierre=True: completa hasta la última fracción para no dejar restos abiertos."""
        espera = K.ESPERA_ORDEN_LIMITE if espera is None else espera
        restante, lleno, costo, comision, a_mercado = qty, 0.0, 0.0, 0.0, False
        minq = 0.0 if cierre else self.minimos(sym)["cantidad"]
        fin = time.time() + espera
        while restante > max(minq, 1e-12) and time.time() < fin:
            bid, ask = self.libro(sym)
            px = bid if side == "buy" else ask
            try:
                o = self.ex.create_order(sym, "limit", side, self.redondear(sym, restante), px,
                                         {"postOnly": True, "positionSide": pos_side})
            except Exception as e:  # el precio se movió y la orden habría ejecutado al instante: reintenta
                log("   " + t("Orden límite rechazada ({e}), reintento.", e=type(e).__name__))
                time.sleep(2); continue
            hasta = min(fin, time.time() + 30)
            o2 = o
            while time.time() < hasta:
                time.sleep(4)
                o2 = self.ex.fetch_order(o["id"], sym)
                if o2.get("status") == "closed":
                    break
            if o2.get("status") != "closed":
                try:
                    self.ex.cancel_order(o["id"], sym)
                except Exception:
                    pass
                o2 = self.ex.fetch_order(o["id"], sym)
            f = float(o2.get("filled") or 0)
            if f > 0:
                p = float(o2.get("average") or o2.get("price") or px)
                lleno += f; costo += f * p; comision += f * p * K.FEE; restante -= f
        restante = self.redondear(sym, restante)
        if restante > max(minq, 1e-12):
            a_mercado = True
            o = self.ex.create_order(sym, "market", side, restante, None, {"positionSide": pos_side})
            o = self.ex.fetch_order(o["id"], sym) if o.get("average") is None else o
            f = float(o.get("filled") or restante)
            p = float(o.get("average") or self.libro(sym)[1 if side == "buy" else 0])
            lleno += f; costo += f * p; comision += f * p * K.FEE_TAKER
        if lleno:
            e = self.__dict__.setdefault("stats", dict(ordenes=0, mercado=0, comision=0.0, volumen=0.0))
            e["ordenes"] += 1; e["mercado"] += int(a_mercado); e["comision"] += comision; e["volumen"] += costo
        return dict(cantidad=lleno, precio=(costo / lleno) if lleno else None, comision=comision, mercado=a_mercado)

    def poner_stop(self, sym, lado, qty, stop):
        """Stop a mercado puesto en Binance para una posición LONG o SHORT."""
        side = "sell" if lado == "long" else "buy"
        params = {"positionSide": LADO_POS[lado], "workingType": "MARK_PRICE", "stopLossPrice": self.precio_stop(sym, stop)}
        try:
            o = self.ex.create_order(sym, "market", side, self.redondear(sym, qty), None, params)
        except Exception:
            o = self.ex.create_order(sym, "STOP_MARKET", side, self.redondear(sym, qty), None,
                                     {"positionSide": LADO_POS[lado], "workingType": "MARK_PRICE",
                                      "stopPrice": self.precio_stop(sym, stop)})
        return o["id"]

    def cancelar_stop(self, sym, oid):
        for params in ({}, {"trigger": True}, {"stop": True}):
            try:
                self.ex.cancel_order(oid, sym, params)
                return True
            except Exception:
                continue
        return False

    def trades_desde(self, sym, desde_ms):
        try:
            return self.ex.fetch_my_trades(sym, since=desde_ms)
        except Exception:
            return []


# ------------------------------------------------------------------ un paso del bot en vivo
def _registrar_cierre(key, p, salida, cantidad, comision, t_ms, motivo):
    sg = 1 if p["side"] == "long" else -1
    pnl = sg * (salida - p["e"]) * cantidad - comision
    return dict(side=p["side"], entrada_t=p["t"], salida_t=t_ms, entrada=p["e"], salida=salida, cantidad=cantidad,
                pnl=pnl, motivo=motivo)


def step_live(br, st):
    """Igual que PT.step, pero las órdenes van a Binance y los stops los ejecuta el exchange."""
    ahora = int(time.time() * 1000)
    velas = {}
    for asset, sym in K.SYMBOLS.items():
        rows = br.velas(sym)
        velas[asset] = prepare([r for r in rows if r[0] + K.BAR_MS <= ahora], K.BAR_MS, K.HTF_MS)
    PT.aplicar_capital(st)
    def minimo(k, a):  # monto que necesita la estrategia k en la moneda a para llegar al mínimo de Binance hoy
        from engine import STRATS
        try:
            D, mins = velas[a], br.minimos(K.SYMBOLS[a])
            px, atr = D["C"][-1], D["ATR"][-1]
            return max(mins["costo"], mins["cantidad"] * px) * STRATS[k]["stop_atr"] * atr / px / K.RISK_PER_TRADE
        except Exception:
            return None

    act, asig = PT.plan(st, velas, minimo)
    PT.aplicar_asignacion(st, act, asig)
    PT.aplicar_capital(st)
    notas = br.preparar(list(K.SYMBOLS.values()))
    for n in notas:
        PT.log(t("Aviso de Binance: {n}", n=n))
    frenado = st.get("frenado", False)
    prices, total, items, vela_txt = {}, 0.0, [], None
    reales = br.posiciones(list(K.SYMBOLS.values()))
    for asset, sym in K.SYMBOLS.items():
        D = velas[asset]
        activas = act[asset]
        i = D["n"] - 1
        nueva = st["last_bar"].get(asset) is None or D["T"][i] > st["last_bar"][asset]
        bid, ask = br.libro(sym)
        prices[asset] = (bid + ask) / 2
        if nueva:
            vela_txt = t("{a} a {b}", a=f"{datetime.fromtimestamp(D['T'][i] / 1000):%H:%M}",
                         b=f"{datetime.fromtimestamp(D['T'][i] / 1000 + 3600):%H:%M}")

        # 1) ¿Binance ejecutó algún stop desde la última revisión?
        for lado in ("long", "short"):
            claves = [k for k, v in st["sleeves"].items() if k.startswith(asset + "_") and v["pos"] and v["pos"]["side"] == lado]
            esperado = sum(st["sleeves"][k]["pos"]["q"] for k in claves)
            hay = reales.get((sym, lado), 0.0)
            if not claves or hay >= esperado * 0.999:
                continue
            desde = st.get("ultima_revision_ms", ahora - 3 * 3600 * 1000)
            ts = [t for t in br.trades_desde(sym, desde) if (t.get("info", {}).get("positionSide") == LADO_POS[lado])
                  and t.get("side") == ("sell" if lado == "long" else "buy")]
            faltante = esperado - hay
            # se cerraron primero los stops más cercanos al precio
            for k in sorted(claves, key=lambda k: abs(st["sleeves"][k]["pos"]["stop"] - prices[asset])):
                if faltante <= 1e-12:
                    break
                p = st["sleeves"][k]["pos"]
                px = (sum(float(t["price"]) * float(t["amount"]) for t in ts) / sum(float(t["amount"]) for t in ts)) if ts else p["stop"]
                tr = _registrar_cierre(k, p, px, p["q"], p["q"] * px * K.FEE_TAKER, ahora, "stop")
                st["sleeves"][k]["equity"] += tr["pnl"]
                tr["capital"] = st["sleeves"][k]["equity"]
                st["sleeves"][k]["pos"] = None; st["sleeves"][k]["pending"] = None
                faltante -= p["q"]
                PT.log(t("{k}: Binance ejecutó el stop de la {l} a {p} ({r} USDT).", k=k, l=PT.lado(p["side"]),
                         p=PT._pr(px), r=num(tr["pnl"], 2, True)))
                _guardar_trade(k, tr)

        if not nueva:
            for s in PT.NOMBRES:
                ss = st["sleeves"][f"{asset}_{s}"]
                total += ss["equity"] + (((1 if ss["pos"]["side"] == "long" else -1) * (prices[asset] - ss["pos"]["e"]) * ss["pos"]["q"]) if ss["pos"] else 0)
            continue

        # 2) decisiones en la última vela cerrada
        for s in PT.NOMBRES:
            key = f"{asset}_{s}"
            ss = st["sleeves"][key]
            activa = s in activas and not frenado
            if not ss["pos"] and (s not in activas or ss["equity"] <= 1e-9):
                continue  # estrategia inactiva o sin monto asignado en esta moneda
            sl = Sleeve(s, K.RISK_PER_TRADE, K.MAX_LEVERAGE, K.FEE, 0.0, ss["equity"], ss["pos"], None,
                        activa=activa, simular_stops=False)
            stop_antes = ss["pos"]["stop"] if ss["pos"] else None
            sl.on_bar(D, i)
            cond = explain(D, i, s) if s in activas else []
            partes, accion = [], None
            pend = sl.pending
            # salida o reversa
            if sl.pos and pend and (pend == "exit" or pend != sl.pos["side"]):
                p = sl.pos
                r = br.ejecutar(sym, "sell" if p["side"] == "long" else "buy", p["q"], LADO_POS[p["side"]], PT.log, cierre=True)
                if p.get("stop_id"):
                    br.cancelar_stop(sym, p["stop_id"])
                if r["cantidad"] > 0:
                    tr = _registrar_cierre(key, p, r["precio"], r["cantidad"], r["comision"], ahora,
                                           "salida_señal" if pend == "exit" else "reversa")
                    sl.equity += tr["pnl"]; tr["capital"] = sl.equity; _guardar_trade(key, tr)
                    partes.append(t("cerró la {l} a {p} ({r} USDT)", l=PT.lado(p["side"]), p=PT._pr(r["precio"]),
                                    r=num(tr["pnl"], 2, True)))
                    accion = "cierra"
                sl.pos = None
            # entrada
            if pend in ("long", "short") and not sl.pos and activa:
                bid, ask = br.libro(sym)
                ref = ask if pend == "long" else bid
                dist = sl.S["stop_atr"] * D["ATR"][i]
                q_ideal = min(sl.equity * K.RISK_PER_TRADE / dist, sl.equity * K.MAX_LEVERAGE / ref)
                q = br.redondear(sym, q_ideal)
                mins = br.minimos(sym)
                if q <= 0 or q < mins["cantidad"] or q * ref < mins["costo"]:
                    accion = "no_abre"
                    partes.append(t("había señal de {l}, pero el tamaño ({q} USDT) es menor al mínimo de Binance para "
                                    "{a} ({m} USDT)", l=PT.lado(pend), q=PT._pr(q_ideal * ref), a=asset, m=PT._pr(mins["costo"])))
                else:
                    r = br.ejecutar(sym, "buy" if pend == "long" else "sell", q, LADO_POS[pend], PT.log)
                    if r["cantidad"] > 0:
                        e = r["precio"]
                        stop = e - dist if pend == "long" else e + dist
                        sl.equity -= r["comision"]
                        sl.pos = dict(side=pend, q=r["cantidad"], e=e, stop=stop, bars=0, t=ahora, atr0=D["ATR"][i])
                        try:
                            sl.pos["stop_id"] = br.poner_stop(sym, pend, r["cantidad"], stop)
                        except Exception as ex_:
                            PT.log(t("{k}: ¡no se pudo poner el stop en Binance! ({e}) Se cierra la posición por seguridad.",
                                     k=key, e=ex_))
                            r2 = br.ejecutar(sym, "sell" if pend == "long" else "buy", r["cantidad"], LADO_POS[pend], PT.log, espera=0, cierre=True)
                            tr = _registrar_cierre(key, sl.pos, r2["precio"], r2["cantidad"], r2["comision"], ahora, "sin_stop")
                            sl.equity += tr["pnl"]; tr["capital"] = sl.equity; _guardar_trade(key, tr); sl.pos = None
                        if sl.pos:
                            accion = "abre"
                            partes.append(t("abrió {l} de {q} USDT a {e} con stop en {s} en Binance", l=PT.lado(pend),
                                            q=PT._pr(r["cantidad"] * e), e=PT._pr(e), s=PT._pr(stop))
                                          + (t(" (completada a mercado)") if r["mercado"] else ""))
            elif sl.pos and stop_antes is not None and accion is None:
                p = sl.pos
                accion = "mantiene"
                txt = t("mantiene la {l} (entrada {e}, stop {s}", l=PT.lado(p["side"]), e=PT._pr(p["e"]), s=PT._pr(p["stop"]))
                if abs(p["stop"] - stop_antes) / p["e"] > 0.001:  # trailing: mueve el stop en Binance
                    try:
                        nuevo = br.poner_stop(sym, p["side"], p["q"], p["stop"])
                        if p.get("stop_id"):
                            br.cancelar_stop(sym, p["stop_id"])
                        p["stop_id"] = nuevo
                        txt += t(", stop movido en Binance desde {s}", s=PT._pr(stop_antes))
                    except Exception as ex_:
                        p["stop"] = stop_antes
                        txt += t(", no se pudo mover el stop ({e})", e=type(ex_).__name__)
                else:
                    p["stop"] = stop_antes  # movimiento menor al 0,1 %: queda el stop que ya está en Binance
                partes.append(txt + ")")
            if accion is None:
                accion = "no_abre" if activa else "inactiva"
                cumplen = sum(1 for _, ok in cond if ok)
                if frenado and s in activas:
                    partes.append(t("no abre: el bot está frenado por el límite de pérdida"))
                elif cumplen < len(cond):
                    partes.append(t("no abre: se cumplen {c} de {n} condiciones", c=cumplen, n=len(cond)))
                else:
                    partes.append(t("no abre"))
            if s not in activas:
                partes.append(t("estrategia no elegida para este mercado: solo maneja la posición que ya tenía")
                              if PT.modo_auto() else t("estrategia desactivada: solo maneja la posición que ya tenía"))
            items.append(dict(activo=asset, clave=s, estrategia=PT.nombre(s), accion=accion, texto="; ".join(partes),
                              condiciones=[[c, bool(ok)] for c, ok in cond]))
            ss.update(equity=sl.equity, pos=sl.pos, pending=None)
            total += sl.mark(prices[asset])
        st["last_bar"][asset] = D["T"][i]

    procesadas = {f"{a}_{s}" for a in K.SYMBOLS for s in PT.NOMBRES}
    for k, v in st["sleeves"].items():  # partes sin posición que no se procesaron (inactivas o sin monto)
        if k in procesadas and not v["pos"] and (k.split("_", 1)[1] not in act[k.split("_", 1)[0]] or v["equity"] <= 1e-9):
            total += v["equity"]
    total += st.get("libre", 0.0)
    st["ultima_revision_ms"] = ahora
    PT.sumar_ordenes(st, getattr(br, "stats", {}))
    br.stats = dict(ordenes=0, mercado=0, comision=0.0, volumen=0.0)
    cap0 = st.get("ref_limite") or PT.base_capital(st)  # al reanudar se mide desde el saldo de ese momento
    if not frenado and total < cap0 * (1 - K.LIMITE_PERDIDA):
        st["frenado"] = True
        PT.log(t("LÍMITE DE PÉRDIDA: la cuenta del bot bajó a {a} USDT (base {b}). No abre más operaciones hasta que "
                 "lo reanudes desde la aplicación.", a=num(total), b=num(cap0)))
    PT.save_state(st)
    if items:
        PT.log(t("Revisión de la vela de {v} ({m}):", v=vela_txt, m=t(K.NOMBRE_MODO[K.MODO])))
        for it in items:
            PT.log(f"   {it['activo']} {it['estrategia']}: {it['texto']}.")
        with open(K.DECISIONES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"hora": datetime.now().isoformat(timespec="seconds"), "vela": vela_txt, "items": items},
                               ensure_ascii=False) + "\n")
    else:
        PT.log(t("Sin velas nuevas desde la última revisión: no hay nada que decidir."))
    PT.append_csv(K.EQUITY_FILE, [{"hora": datetime.now().strftime("%Y-%m-%d %H:%M"), "total": round(total, 2),
                                   "base": round(PT.base_capital(st), 2)}], ["hora", "total", "base"])
    return total, prices


def _guardar_trade(key, tr):
    trc = dict(tr, posicion=key, entrada_t=PT.fmt_t(tr["entrada_t"]), salida_t=PT.fmt_t(tr["salida_t"]))
    PT.append_csv(K.TRADES_FILE, [trc], ["posicion", "side", "entrada_t", "salida_t", "entrada", "salida", "cantidad", "pnl", "motivo", "capital"])


def cerrar_todo(br, st):
    """Cierra a mercado todas las posiciones del bot y cancela sus stops."""
    ahora, cerradas = int(time.time() * 1000), 0
    for key, ss in st["sleeves"].items():
        p = ss["pos"]
        if not p:
            continue
        sym = K.SYMBOLS[key.split("_", 1)[0]]
        if p.get("stop_id"):
            br.cancelar_stop(sym, p["stop_id"])
        r = br.ejecutar(sym, "sell" if p["side"] == "long" else "buy", p["q"], LADO_POS[p["side"]], PT.log, espera=0, cierre=True)
        tr = _registrar_cierre(key, p, r["precio"], r["cantidad"], r["comision"], ahora, "cierre_manual")
        ss["equity"] += tr["pnl"]; tr["capital"] = ss["equity"]; _guardar_trade(key, tr)
        ss["pos"] = None; ss["pending"] = None; cerradas += 1
        PT.log(t("{k}: cerrada a mano desde la aplicación a {p} ({r} USDT).", k=key, p=PT._pr(r["precio"]),
                 r=num(tr["pnl"], 2, True)))
    PT.save_state(st)
    return cerradas


def prueba_ordenes(br, log):
    """Solo cuenta demo: abre la posición mínima en SOL con su stop, la cierra y cancela el stop."""
    sym = K.SYMBOLS["SOL"]
    br.preparar([sym])
    bid, ask = br.libro(sym)
    mins = br.minimos(sym)
    q = br.redondear(sym, max(mins["cantidad"], mins["costo"] * 1.2 / ask))
    log(t("Prueba de órdenes en la cuenta demo: compra de {q} SOL (~{u} USDT).", q=q, u=num(q * ask)))
    r = br.ejecutar(sym, "buy", q, "LONG", log, espera=20)
    log("   " + t("Compra ejecutada: {c} a {p}", c=r["cantidad"], p=num(r["precio"], 3)) + (t(" (a mercado)") if r["mercado"] else t(" (orden límite)")))
    sid = br.poner_stop(sym, "long", r["cantidad"], r["precio"] * 0.95)
    log("   " + t("Stop puesto en Binance a {p} (id {i}).", p=num(r["precio"] * 0.95, 3), i=sid))
    time.sleep(2)
    ok = br.cancelar_stop(sym, sid)
    log("   " + (t("Stop cancelado: sí.") if ok else t("Stop cancelado: NO (revisalo en Binance).")))
    r2 = br.ejecutar(sym, "sell", r["cantidad"], "LONG", log, espera=0, cierre=True)
    log("   " + t("Posición cerrada a {p}. Prueba terminada.", p=num(r2["precio"], 3)))
    return True
