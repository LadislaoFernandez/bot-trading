"""Binance Futuros falso para probar live.py: modo cobertura, post-only, stops, mínimos."""
import itertools, random

class FakeBinance:
    def __init__(self, rows_by_sym, clock, minimos):
        self.rows, self.clock, self.min = rows_by_sym, clock, minimos
        self.pos = {}          # (sym, lado) -> qty
        self.orders, self.ids = {}, itertools.count(1)
        self.trades, self.log = [], []
        self.rechazos_postonly = 0
    # mercado
    def _bar(self, sym):
        vis = [r for r in self.rows[sym] if r[0] <= self.clock["t"]]
        return vis[-1]
    def fetch_ohlcv(self, sym, tf, limit=1500, since=None):
        return [r[:] for r in self.rows[sym] if r[0] <= self.clock["t"]][-limit:]
    def fetch_order_book(self, sym, n=5):
        px = self._bar(sym)[1]  # precio = apertura de la vela en curso
        return {"bids": [[px * 0.9999, 1]], "asks": [[px * 1.0001, 1]]}
    def market(self, sym):
        c, a = self.min[sym]
        return {"limits": {"cost": {"min": c}, "amount": {"min": a}}}
    def amount_to_precision(self, sym, q):
        a = self.min[sym][1]; return str(int(q / a) * a)
    def price_to_precision(self, sym, p): return str(round(p, 4))
    # cuenta
    def set_position_mode(self, h): raise Exception("binanceusdm {\"code\":-4059,\"msg\":\"No need to change position side.\"}")
    def set_margin_mode(self, m, s): pass
    def set_leverage(self, l, s): pass
    def fetch_positions(self, syms):
        return [{"symbol": s, "side": l, "contracts": q} for (s, l), q in self.pos.items() if q > 1e-12]
    def _fill(self, sym, side, q, ps, px):
        lado = ps.lower()
        sg = 1 if (side == "buy") == (lado == "long") else -1
        self.pos[(sym, lado)] = self.pos.get((sym, lado), 0) + sg * q
        assert self.pos[(sym, lado)] >= -1e-9, f"posición negativa {sym} {lado} {self.pos[(sym, lado)]}"
        self.trades.append({"symbol": sym, "side": side, "amount": q, "price": px, "timestamp": self.clock["t"], "info": {"positionSide": ps}})
    def create_order(self, sym, typ, side, q, px, params):
        q = float(q); oid = str(next(self.ids)); ps = params["positionSide"]
        if q * (px or self._bar(sym)[1]) < self.min[sym][0] - 1e-9: raise Exception("notional too small")
        if "stopLossPrice" in params:
            self.orders[oid] = dict(id=oid, sym=sym, side=side, q=q, ps=ps, stop=float(params["stopLossPrice"]), status="open", stopord=True)
            return {"id": oid}
        if typ == "limit":
            if params.get("postOnly") and random.random() < 0.3:
                self.rechazos_postonly += 1; raise Exception("OrderImmediatelyFillable")
            st_ = self.min[sym][1]; fill = q if random.random() < 0.7 else max(st_, int(q / 2 / st_) * st_)  # parcial en lotes
            self._fill(sym, side, fill, ps, px)
            self.orders[oid] = dict(id=oid, status="closed" if fill == q else "open", filled=fill, average=px, price=px)
            return {"id": oid}
        p = self._bar(sym)[1] * (1.0002 if side == "buy" else 0.9998)
        self._fill(sym, side, q, ps, p)
        o = dict(id=oid, status="closed", filled=q, average=p); self.orders[oid] = o; return o
    def fetch_order(self, oid, sym, params=None):
        o = self.orders[oid]; return {"id": oid, "status": o["status"], "filled": o.get("filled"), "average": o.get("average"), "price": o.get("price")}
    def cancel_order(self, oid, sym, params=None):
        o = self.orders.get(oid)
        if not o or o["status"] != "open": raise Exception("Unknown order")
        o["status"] = "canceled"
    def fetch_my_trades(self, sym, since=None):
        return [t for t in self.trades if t["symbol"] == sym and t["timestamp"] >= (since or 0)]
    # simula lo que pasa dentro de la vela: stops que se disparan
    def procesar_vela(self, sym, bar):
        for o in list(self.orders.values()):
            if o.get("stopord") and o["sym"] == sym and o["status"] == "open":
                lado = o["ps"].lower()
                if (lado == "long" and bar[3] <= o["stop"]) or (lado == "short" and bar[2] >= o["stop"]):
                    q = min(o["q"], self.pos.get((sym, lado), 0))
                    if q > 0: self._fill(sym, o["side"], q, o["ps"], o["stop"])
                    o["status"] = "closed"
