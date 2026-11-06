"""Velas de Binance Futuros USDⓈ-M (datos públicos, no requiere API keys)."""
import time


def exchange():
    import ccxt
    return ccxt.binanceusdm({"enableRateLimit": True})


def fetch_range(ex, symbol, timeframe, since_ms, until_ms):
    rows = []
    while since_ms < until_ms:
        batch = ex.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=1500)
        if not batch:
            break
        rows += [r[:5] for r in batch]
        nxt = batch[-1][0] + 1
        if nxt <= since_ms:
            break
        since_ms = nxt
        time.sleep(ex.rateLimit / 1000)
    seen, out = set(), []
    for r in rows:
        if r[0] < until_ms and r[0] not in seen:
            seen.add(r[0]); out.append(r)
    return out


def fetch_recent(ex, symbol, timeframe, limit=1500):
    return [r[:5] for r in ex.fetch_ohlcv(symbol, timeframe, limit=limit)]
