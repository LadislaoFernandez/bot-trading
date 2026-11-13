"""Corazón del bot sin pantalla: precios, lectura del mercado, historial de estrategias, el bot que opera y el
laboratorio. Lo usan la app de Windows (app.py) y el servidor en la nube (servidor.py)."""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

import claves as CL
import config as K
import live as LV
import mercado as M
import paper_trader as PT
from i18n import num, t


def usd(v, d=2, signo=False):
    return f"{num(v, d, signo)}\u00a0USDT"


class PriceFeed(threading.Thread):
    """Consulta precios de Binance Futuros cada 10 s (datos públicos)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.prices, self.updated, self.error = {}, None, None
        self.stop = threading.Event()

    def run(self):
        import ccxt
        ex = ccxt.binanceusdm({"enableRateLimit": True})
        syms = list(K.SYMBOLS.values())
        while not self.stop.is_set():
            try:
                tk = ex.fetch_tickers(syms)
                for a, sym in K.SYMBOLS.items():
                    x = tk.get(sym)
                    if x and x.get("last"):
                        self.prices[a] = {"precio": float(x["last"]), "cambio": x.get("percentage")}
                self.updated, self.error = time.time(), None
            except Exception as e:
                self.error = f"{type(e).__name__}"
            self.stop.wait(10)


class MarketWorker(threading.Thread):
    """Lee el mercado cada 5 minutos y mantiene el historial de estrategias por tipo de mercado."""

    def __init__(self):
        super().__init__(daemon=True)
        self.analisis, self.actualizado, self.error = {}, None, None
        self.minimos = {}  # moneda -> tamaño mínimo de orden en Binance (USDT), de los datos públicos del mercado
        self.historial = M.cargar()
        self.hist_estado, self.hist_prog = ("listo" if self.historial else "pendiente"), (0.0, "")
        self.recalcular, self.stop = threading.Event(), threading.Event()

    def _leer_minimos(self, ex):
        """Tamaño mínimo por orden de cada moneda: el mayor entre el mínimo en USDT y la cantidad mínima por el precio."""
        try:
            if not ex.markets:
                ex.load_markets()
            for a, sym in K.SYMBOLS.items():
                m, px = ex.market(sym), (self.analisis.get(a) or {}).get("precio")
                lim = m.get("limits", {})
                costo = float((lim.get("cost") or {}).get("min") or 5.0)
                cant = float((lim.get("amount") or {}).get("min") or 0.0)
                self.minimos[a] = max(costo, cant * px) if px else costo
        except Exception:
            pass

    def _necesita_historial(self):
        h = self.historial
        from engine import STRATS
        faltan = h and any(s not in h.get("estrategias", {}) for s in STRATS)  # hay estrategias nuevas
        viejo = h and h.get("version") != 2  # historial de antes de la 1.9 (sin resultado por año y semestre)
        mes_nuevo = h and datetime.fromtimestamp(h.get("calculado", 0)).strftime("%Y-%m") != datetime.now().strftime("%Y-%m")
        return (self.recalcular.is_set() or not h or faltan or viejo or mes_nuevo
                or time.time() - h.get("calculado", 0) > 7 * 86400)

    def run(self):
        import ccxt
        from data import fetch_range, fetch_recent
        ex = ccxt.binanceusdm({"enableRateLimit": True})
        prox = 0
        while not self.stop.is_set():
            if time.time() >= prox:
                try:
                    for a, sym in K.SYMBOLS.items():
                        rows = fetch_recent(ex, sym, K.TIMEFRAME, 1500)
                        rows = [r for r in rows if r[0] + K.BAR_MS <= time.time() * 1000]
                        self.analisis[a] = M.analisis(prepare_rows(rows))
                    self._leer_minimos(ex)
                    self.actualizado, self.error = time.time(), None
                except Exception as e:
                    self.error = f"{type(e).__name__}"
                prox = time.time() + 300
            if self._necesita_historial():
                self.recalcular.clear()
                self.hist_estado = "calculando"
                try:
                    desde = int(datetime(2021, 12, 1).timestamp() * 1000)
                    h = M.calcular_historial(lambda a: fetch_range(ex, K.SYMBOLS[a], K.TIMEFRAME, desde, int(time.time() * 1000)),
                                             lambda f, x: setattr(self, "hist_prog", (f, x)))
                    M.guardar(h); self.historial = h; self.hist_estado = "listo"
                except Exception as e:
                    self.hist_estado = "error"; self.hist_prog = (0.0, f"{type(e).__name__}: {e}"[:120])
            self.stop.wait(5)


def prepare_rows(rows):
    from engine import prepare
    return prepare(rows, K.BAR_MS, K.HTF_MS)


# ------------------------------------------------------------------ control del bot
class Bot:
    def __init__(self):
        self.thread, self.stop_ev, self.wake_ev = None, None, None

    def corriendo(self):
        return self.thread is not None and self.thread.is_alive()

    def iniciar(self):
        if self.corriendo():
            return
        self.stop_ev, self.wake_ev = threading.Event(), threading.Event()
        modo, stop, wake = K.MODO, self.stop_ev, self.wake_ev
        PT.STATUS.update(estado="revisando", ultimo_error=None, proxima_revision=None)

        def correr():
            st = PT.load_state()
            if modo == "simulado":
                PT.run_loop(st, stop, None, wake, ajuste=PT.ajustar_stops); return
            cred = CL.cargar(modo)
            if not cred:
                PT.STATUS.update(estado="detenido",
                                 ultimo_error=t("Faltan las claves de API de este modo. Cargalas en Configuración."))
                return
            try:
                br = LV.Broker(modo, *cred)
                if not os.path.exists(K.STATE_FILE):  # primera vez en este modo: controla que alcance el saldo
                    libre = br.saldo()["libre"]
                    if libre < K.INITIAL_CAPITAL:
                        PT.STATUS.update(estado="detenido", ultimo_error=t(
                            "El saldo libre en Binance ({l}) es menor al capital del bot ({c}).",
                            l=usd(libre), c=usd(K.INITIAL_CAPITAL)))
                        return
            except Exception as e:
                PT.STATUS.update(estado="detenido",
                                 ultimo_error=(t("No se pudo conectar a Binance:") + f" {type(e).__name__}: {e}")[:220])
                PT.log((t("No se pudo conectar a Binance ({m}):", m=t(K.NOMBRE_MODO[modo])) + f" {e}")[:300])
                return
            self.broker = br
            PT.run_loop(st, stop, None, wake, paso=LV.step_live, cliente=br, ajuste=LV.ajustar_stops)

        self.thread = threading.Thread(target=correr, daemon=True)
        self.thread.start()

    def detener(self):
        if self.corriendo() and self.stop_ev:
            self.stop_ev.set()
            self.thread.join(timeout=15)

    def revisar_ahora(self):
        if self.corriendo() and self.wake_ev:
            self.wake_ev.set()


# ------------------------------------------------------------------ widgets dibujados


# ------------------------------------------------------------------ laboratorio (laboratorio.py)
class Laboratorio:
    """Lanza el laboratorio una vez por semana (o a pedido) como proceso aparte, con prioridad baja."""

    def __init__(self, prueba=False):
        self.prueba, self.lanzado = prueba, 0.0

    @staticmethod
    def ajustes():
        return PT.leer_ajustes().get("laboratorio", {}) or {}

    @staticmethod
    def estado():
        import archivos
        return archivos.leer_json("laboratorio_estado.json", {}, segundos=0.3) or {}

    def corriendo(self, st=None):
        st = st or self.estado()
        if time.time() - self.lanzado < 180 and st.get("inicio", 0) < self.lanzado:
            return True  # recién lanzado: todavía no escribió su estado
        return bool(st.get("corriendo")) and time.time() - st.get("latido", 0) < 300

    def tick(self):
        """Lo llama la app o el servidor cada 5 minutos: lanza la búsqueda semanal si corresponde."""
        if self.prueba or not self.ajustes().get("activo"):
            return False
        st = self.estado()
        if self.corriendo(st):
            return False
        fallo = str(st.get("mensaje", "")).startswith("error") or (st and not st.get("fin"))
        ultimo = max(st.get("fin", 0), st.get("latido", 0), self.lanzado)
        espera = 3600 if fallo else 7 * 86400  # si la última búsqueda falló, reintenta en 1 hora
        if time.time() - ultimo >= espera:
            return self.lanzar()
        return False

    def lanzar(self):
        if self.prueba or self.corriendo():
            return False
        flags = 0x08000000 if os.name == "nt" else 0  # sin ventana
        extra = {} if os.name == "nt" else {"preexec_fn": lambda: os.nice(10)}
        with open("laboratorio.log", "a", encoding="utf-8") as out:
            subprocess.Popen([sys.executable, os.path.abspath("laboratorio.py"), "--minutos", "30"], cwd=os.getcwd(),
                             stdout=out, stderr=out, creationflags=flags, **extra)
        self.lanzado = time.time()
        PT.log(t("Laboratorio de estrategias: búsqueda iniciada (30 minutos)."))
        return True

    @staticmethod
    def candidatas():
        out = []
        if os.path.isdir("candidatas"):
            for fn in sorted(os.listdir("candidatas")):
                if fn.startswith("LAB_") and fn.endswith(".json"):
                    try:
                        with open(os.path.join("candidatas", fn), encoding="utf-8") as f:
                            d = json.load(f)
                        if d.get("examen"):  # las del laboratorio anterior no se muestran (el laboratorio las descarta)
                            out.append(d)
                    except (OSError, ValueError):
                        pass
        return sorted(out, key=lambda d: -d.get("numero", 0))
