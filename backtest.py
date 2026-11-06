"""Backtest del portafolio con detalle mensual.

  python backtest.py                         # 2026 (enero a hoy)
  python backtest.py --desde 2025-01-01 --hasta 2026-01-01
"""
import argparse
from datetime import datetime, timezone

import config as K
from data import exchange, fetch_range
from engine import Sleeve, prepare


def ms(s):
    return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def run(desde, hasta, rows_by_asset):
    per = K.INITIAL_CAPITAL / (len(K.SYMBOLS) * len(K.STRATEGIES))
    months, results = {}, {}
    for asset, rows in rows_by_asset.items():
        D = prepare(rows, K.BAR_MS, K.HTF_MS)
        for st in K.STRATEGIES:
            sl, last = Sleeve(st, K.RISK_PER_TRADE, K.MAX_LEVERAGE, K.FEE, K.SLIPPAGE, per), None
            trades = []
            for i in range(1, D["n"]):
                if not (desde <= D["T"][i] < hasta):
                    continue
                last = i
                sl.on_bar(D, i)
                trades += sl.closed; sl.closed = []
                key = datetime.fromtimestamp(D["T"][i] / 1000, timezone.utc).strftime("%Y-%m")
                months.setdefault(key, {})[f"{asset}_{st}"] = sl.mark(D["C"][i])
            if sl.pos:
                sl.close(D["C"][last], D["T"][last], "fin_backtest"); trades += sl.closed
            results[f"{asset}_{st}"] = (sl.equity, len(trades))
    return months, results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2026-01-01")
    ap.add_argument("--hasta", default=None)
    ap.add_argument("--historia", default="2021-12-01", help="desde cuándo bajar velas para calentar indicadores")
    a = ap.parse_args()
    desde = ms(a.desde)
    hasta = ms(a.hasta) if a.hasta else int(datetime.now(timezone.utc).timestamp() * 1000) // K.BAR_MS * K.BAR_MS
    ex = exchange()
    rows = {}
    for asset, sym in K.SYMBOLS.items():
        print(f"Bajando velas {K.TIMEFRAME} de {asset}...")
        rows[asset] = fetch_range(ex, sym, K.TIMEFRAME, ms(a.historia), hasta)
        r = rows[asset]
        print(f"  {len(r)} velas ({datetime.fromtimestamp(r[0][0]/1000, timezone.utc):%Y-%m-%d} a {datetime.fromtimestamp(r[-1][0]/1000, timezone.utc):%Y-%m-%d})" if r else "  0 velas")
    months, results = run(desde, hasta, rows)

    print(f"\nCapital inicial {K.INITIAL_CAPITAL:.2f} USDT | riesgo {K.RISK_PER_TRADE*100:.0f}% | comisión {K.FEE*100:.2f}%\n")
    print(f"{'Mes':<9}{'Cuenta':>10}{'Var.':>9}")
    prev = K.INITIAL_CAPITAL
    for m in sorted(months):
        tot = sum(months[m].values())
        print(f"{m:<9}{tot:>10.2f}{(tot / prev - 1) * 100:>8.1f}%")
        prev = tot
    print("\nPor posición:")
    for k, (eq, n) in results.items():
        print(f"  {k:<14} {eq:>8.2f}  ({n} operaciones)")
    print(f"\nTotal final: {sum(e for e, _ in results.values()):.2f} USDT")


if __name__ == "__main__":
    main()
