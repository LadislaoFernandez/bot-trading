"""Bot de trading en un servidor (por ejemplo Oracle Cloud, gratis), sin pantalla, prendido las 24 horas.

Las apps de control (Windows y Android) se conectan por HTTPS con un código de conexión: ven todo y pueden prender o
apagar el bot, el piloto, el laboratorio, etc. Las claves de Binance se cargan EN el servidor (por consola) y nunca viajan
por la red.

  python3 servidor.py preparar [--ip IP] [--puerto 8443]   crea el certificado y el token (una sola vez)
  python3 servidor.py codigo                               muestra el código de conexión para las apps
  python3 servidor.py claves demo|real                     carga las claves de Binance (Ed25519 o HMAC)
  python3 servidor.py probar demo|real                     prueba la conexión con Binance
  python3 servidor.py modo simulado|demo|real              elige el modo de operación
  python3 servidor.py estado                               resumen rápido
  python3 servidor.py correr                               corre el bot y la API (lo usa el servicio systemd)

Seguridad de la API:
  - HTTPS con un certificado propio; las apps lo "fijan" con la huella que viene en el código de conexión, así que nadie
    puede hacerse pasar por el servidor.
  - Cada pedido lleva un token de 256 bits. Sin token, el servidor no responde nada útil (y frena los reintentos).
  - Las claves de Binance nunca se mandan ni se reciben por la API.
"""
import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import ssl
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import config as K  # noqa: E402
import paper_trader as PT  # noqa: E402
from i18n import t  # noqa: E402

CONFIG = "servidor_config.json"
CERT, CLAVE = "servidor.crt", "servidor.key"
PREFIJO_CODIGO = "BOT1-"
API_VERSION = 1


# ------------------------------------------------------------------ configuración del servidor
def leer_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def guardar_config(c):
    fd = os.open(CONFIG + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)
    os.replace(CONFIG + ".tmp", CONFIG)


def ip_publica():
    import urllib.request
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://checkip.amazonaws.com"):
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                ip = r.read().decode().strip()
                if ip.count(".") == 3:
                    return ip
        except Exception:
            continue
    return None


def crear_certificado(ip):
    """Certificado propio (10 años) para la IP del servidor. La clave privada queda con permisos 600."""
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    k = ec.generate_private_key(ec.SECP256R1())
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "bot-trading")])
    alt = [x509.DNSName("bot-trading")]
    try:
        alt.append(x509.IPAddress(ipaddress.ip_address(ip)))
    except ValueError:
        pass
    ahora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(k.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(ahora - timedelta(days=1))
            .not_valid_after(ahora + timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False).sign(k, hashes.SHA256()))
    fd = os.open(CLAVE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()))
    with open(CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def capital_minimo(snap, minimos, analisis, piloto_base):
    """Capital mínimo recomendado para que todas las partes lleguen al mínimo de orden de Binance (misma cuenta que el
    control de Windows), o None si todavía no hay datos del mercado. Lo usa la app de Android, que no tiene el motor."""
    try:
        return _capital_minimo(snap, minimos, analisis, piloto_base)
    except Exception:
        return None


def _capital_minimo(snap, minimos, analisis, piloto_base):
    from engine import STRATS
    au = snap.get("auto_estado") or {}
    estr = (au.get("dentro") if au.get("dentro") is not None else piloto_base) if snap.get("auto") else snap.get("activas")
    partes = [(x, a) for x in (estr or []) for a in K.SYMBOLS]
    if not partes or K.MODO == "simulado":
        return None
    mins = {}
    for x, a in partes:
        mn, an = (minimos or {}).get(a), (analisis or {}).get(a)
        if not mn or not an or not an.get("atr_pct") or x not in STRATS:
            return None
        mins[(x, a)] = mn * STRATS[x]["stop_atr"] * an["atr_pct"] / K.RISK_PER_TRADE
    (x, a), m = max(mins.items(), key=lambda i: i[1])
    por_parte = m * 1.25
    return dict(total=por_parte * len(partes), por_parte=por_parte, partes=len(partes), estrategia=x, activo=a,
                disponible=snap.get("saldo_cerrado"))


def eventos_operaciones(carpeta=".", maximo=40):
    """Aperturas y cierres de operaciones del modo actual, del más reciente al más viejo (para las notificaciones del
    celular). Cada evento tiene un id estable: la apertura de una posición tiene el mismo id mientras está abierta y
    después de cerrarse, así la app avisa una sola vez de cada cosa."""
    import app_data as A
    ev = []
    for o in A.operaciones(carpeta)[:maximo]:
        base = dict(activo=o["activo"], estrategia=o["estrategia"], lado=o["lado"])
        ev.append(dict(base, id=f"c|{o['activo']}|{o['clave']}|{o['entrada_t']}|{o['salida_t']}", tipo="cierra",
                       hora=o["salida_t"], precio=o["salida"], pnl=o["pnl"], motivo=o["motivo"]))
        ev.append(dict(base, id=f"a|{o['activo']}|{o['clave']}|{o['entrada_t']}", tipo="abre", hora=o["entrada_t"],
                       precio=o["entrada"]))
    st = A.leer_estado(carpeta) or {}
    for k, ss in (st.get("sleeves") or {}).items():
        p = ss.get("pos")
        if not p or not p.get("t"):
            continue
        a, s = k.split("_", 1)
        hora = PT.fmt_t(p["t"])
        ev.append(dict(id=f"a|{a}|{s}|{hora}", tipo="abre", hora=hora, activo=a, estrategia=PT.nombre(s),
                       lado=p["side"], precio=p["e"], stop=p.get("stop"), tamano=p["q"] * p["e"]))
    unicos = {}
    for e in ev:  # la apertura de una posición abierta trae stop y tamaño: esa versión gana
        if e["id"] not in unicos or "stop" in e:
            unicos[e["id"]] = e
    return sorted(unicos.values(), key=lambda e: (e["hora"], e["tipo"] == "cierra"), reverse=True)[:maximo]


def codigo_conexion(c):
    datos = {"h": c["ip"], "p": c["puerto"], "t": c["token"], "f": c["huella"]}
    return PREFIJO_CODIGO + base64.urlsafe_b64encode(json.dumps(datos, separators=(",", ":")).encode()).decode().rstrip("=")


# ------------------------------------------------------------------ el servicio (bot + mercado + laboratorio)
class Servicio:
    def __init__(self):
        from nucleo import Bot, Laboratorio, MarketWorker, PriceFeed
        PT.configurar_modo(PT.leer_ajustes().get("modo", "simulado"))
        self.bot, self.feed, self.mkt, self.lab = Bot(), PriceFeed(), MarketWorker(), Laboratorio()
        self.cache, self.cache_t, self.lock = None, 0.0, threading.Lock()
        self.actualizacion = {"estado": "sin revisar"}
        self.salir = threading.Event()
        self.codigo_salida = 0

    def arrancar(self):
        self.feed.start(); self.mkt.start()
        if PT.leer_ajustes().get("bot_activo", True):
            self.bot.iniciar()
        threading.Thread(target=self._tareas, daemon=True).start()
        threading.Thread(target=self._push, daemon=True).start()

    def _push(self):
        """Cada 15 segundos: si hubo aperturas o cierres nuevos, avisa al celular por Firebase (push)."""
        import push
        fb, error_previo = None, None
        while not self.salir.is_set():
            try:
                if push.configurado():
                    fb = fb or push.Firebase()
                    push.ciclo(fb, eventos_operaciones("."), t(K.NOMBRE_MODO[K.MODO]), K.VERSION, log=PT.log)
                error_previo = None
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"[:300]
                if msg != error_previo:  # no llena el registro con el mismo error cada 15 segundos
                    PT.log(f"Avisos al celular: {msg}")
                error_previo, fb = msg, None
            self.salir.wait(15)

    def _tareas(self):
        """Cada 5 minutos: laboratorio semanal. Cada hora: busca actualizaciones (y las instala si está activado)."""
        prox_act = time.time() + 120
        while not self.salir.is_set():
            try:
                self.lab.tick()
            except Exception as e:
                PT.log(f"Laboratorio: {e}")
            if time.time() >= prox_act:
                prox_act = time.time() + 3600
                self.buscar_actualizacion(instalar=PT.leer_ajustes().get("instalar_actualizaciones_auto", True))
            self.salir.wait(300)

    def buscar_actualizacion(self, instalar=False):
        import actualizador
        try:
            info = actualizador.buscar()
        except Exception as e:
            self.actualizacion = {"estado": "error", "detalle": f"{type(e).__name__}"}
            return self.actualizacion
        if not info:
            self.actualizacion = {"estado": "al día", "version": K.VERSION, "hora": time.time()}
            return self.actualizacion
        self.actualizacion = {"estado": "disponible", "version": info["version"], "notas": info.get("notas", "")[:2000]}
        if instalar:
            try:
                actualizador.instalar(info)
                PT.log(t("Actualización a la versión {v} instalada en el servidor. Se reinicia.", v=info["version"]))
                self.actualizacion = {"estado": "instalada", "version": info["version"]}
                self.reiniciar()
            except Exception as e:
                self.actualizacion = {"estado": "error", "detalle": f"{type(e).__name__}: {e}"[:300]}
        return self.actualizacion

    def reiniciar(self):
        """Detiene todo y sale; systemd lo vuelve a arrancar (Restart=always) con el código nuevo."""
        def _salir():
            time.sleep(1.5)
            self.bot.detener(); self.feed.stop.set(); self.mkt.stop.set()
            self.codigo_salida = 3
            self.salir.set()
        threading.Thread(target=_salir, daemon=True).start()

    @staticmethod
    def _estado_push():
        import push
        return {"configurado": push.configurado(), "celulares": len(push.tokens())}

    # ---------- lo que leen las apps
    def estado(self):
        import alertas
        import app_data as A
        import mercado as M
        with self.lock:
            if self.cache and time.time() - self.cache_t < 2:
                return self.cache
            snap = A.snapshot(".", dict(self.feed.prices), PT.STATUS)
            for k in ("curva", "decisiones"):
                snap.pop(k, None)
            ops = snap.pop("operaciones", [])
            snap["ultimas_operaciones"] = ops[:30]  # vienen de la más reciente a la más vieja
            aj = PT.leer_ajustes()
            hist = self.mkt.historial or {}
            import auto as AU
            out = dict(
                api=API_VERSION, version=K.VERSION, modo=K.MODO, nombre_modo=t(K.NOMBRE_MODO[K.MODO]),
                servidor=True, hora=time.time(),
                bot=dict(corriendo=self.bot.corriendo(), **{k: v for k, v in PT.STATUS.items()}),
                snap=snap,
                mercado=dict(analisis=self.mkt.analisis, minimos=self.mkt.minimos, actualizado=self.mkt.actualizado,
                             error=self.mkt.error, hist_estado=self.mkt.hist_estado, hist_prog=list(self.mkt.hist_prog)),
                historial=dict(calculado=hist.get("calculado"), desde=hist.get("desde"), estrategias={
                    k: dict(anios=v.get("anios"), semestres=v.get("semestres"),
                            mensual={m: x for m, x in (v.get("mensual") or {}).items() if m >= "2024-01"})
                    for k, v in (hist.get("estrategias") or {}).items()}),
                nombres={k: M.nombre_estrategia(k) for k in PT.NOMBRES},
                retiradas=list(K.RETIRADAS), piloto_base=AU.base(), meses_histeresis=AU.MESES_HISTERESIS,
                alertas=alertas.listar()[:40], sin_leer=len(alertas.listar(solo_sin_leer=True)),
                laboratorio=dict(ajustes=self.lab.ajustes(), estado=self.lab.estado(), corriendo=self.lab.corriendo(),
                                 candidatas=self.lab.candidatas()),
                riesgo=dict(por_operacion=K.RISK_PER_TRADE, limite_perdida=K.LIMITE_PERDIDA,
                            espera_limite=getattr(K, "ESPERA_ORDEN_LIMITE", None)),
                capital=aj.get("capital", {}),
                capital_minimo=capital_minimo(snap, self.mkt.minimos, self.mkt.analisis, AU.base()),
                claves={m: __import__("claves").hay(m) for m in ("demo", "real")},
                actualizacion=self.actualizacion,
                actualizaciones_auto=bool(aj.get("instalar_actualizaciones_auto", True)),
                push=self._estado_push(),
            )
            self.cache, self.cache_t = out, time.time()
            return out

    def detalle(self, que):
        import app_data as A
        if que == "curva":
            return {"curva": A.curva_capital(".")}
        if que == "operaciones":
            return {"operaciones": A.operaciones(".")}
        if que == "decisiones":
            return {"decisiones": A.decisiones(".")}
        if que == "registro":
            return {"lineas": A.leer_log(".", 400)}
        if que == "eventos":
            return {"eventos": eventos_operaciones("."), "modo": K.MODO, "nombre_modo": t(K.NOMBRE_MODO[K.MODO]),
                    "version": K.VERSION}
        raise KeyError(que)

    # ---------- lo que pueden hacer las apps
    def accion(self, d):
        a = d.get("accion")
        self.cache = None
        if a == "push_registrar":
            import push
            push.registrar(str(d.get("token") or ""), str(d.get("version") or "") or None)
            return "ok" if push.configurado() else "sin_firebase"
        if a == "push_quitar":
            import push
            push.quitar(str(d.get("token") or "")); return "ok"
        if a == "iniciar":
            PT.guardar_ajustes(bot_activo=True); self.bot.iniciar()
            PT.log(t("Bot iniciado desde la app de control.")); return "ok"
        if a == "detener":
            PT.guardar_ajustes(bot_activo=False); self.bot.detener()
            PT.log(t("Bot detenido desde la app de control.")); return "ok"
        if a == "revisar":
            if not self.bot.corriendo():
                raise ValueError(t("El bot está detenido."))
            self.bot.revisar_ahora(); return "ok"
        if a == "piloto":
            activo = bool(d.get("activo"))
            PT.guardar_auto(activo=activo)
            PT.log(t("Piloto automático encendido desde la app de control.") if activo else
                   t("Piloto automático apagado desde la app de control."))
            self.bot.revisar_ahora(); return "ok"
        if a == "riesgo":
            r = dict(por_operacion=float(d["por_operacion"]), limite_perdida=float(d["limite_perdida"]),
                     espera_limite=int(d.get("espera_limite") or getattr(K, "ESPERA_ORDEN_LIMITE", 180)))
            if not (0.005 <= r["por_operacion"] <= 0.10 and 0.05 <= r["limite_perdida"] <= 0.9 and 10 <= r["espera_limite"] <= 900):
                raise ValueError(t("Valores fuera de rango."))
            PT.guardar_ajustes(riesgo=r)
            corriendo = self.bot.corriendo()
            self.bot.detener(); PT.configurar_modo(K.MODO)
            if corriendo:
                self.bot.iniciar()
            PT.log(t("Riesgo cambiado desde la app de control: {p} % por operación, límite de pérdida {l} %, espera de la "
                     "orden límite {e} s.", p=round(r["por_operacion"] * 100, 1), l=round(r["limite_perdida"] * 100),
                     e=r["espera_limite"]))
            return "ok"
        if a == "capital":
            valor = round(float(d["valor"]), 2)
            if valor < 10:
                raise ValueError(t("El capital mínimo es 10 USDT."))
            if not PT.leer_ajustes().get("auto", {}).get("activo"):
                raise ValueError(t("Con el piloto apagado, el capital se cambia desde la app de Windows conectada a este "
                                   "equipo, porque hay que revisar los montos de cada estrategia. Encendé el piloto o "
                                   "cambialo en el servidor."))
            caps = PT.leer_ajustes().get("capital", {}); caps[K.MODO] = valor
            PT.guardar_ajustes(capital=caps); PT.configurar_modo(K.MODO)
            PT.log(t("Capital de {m} cambiado a {v} USDT desde la app de control.", m=t(K.NOMBRE_MODO[K.MODO]), v=valor))
            self.bot.revisar_ahora(); return "ok"
        if a == "reanudar":
            st = PT.load_state()
            if not st.get("frenado"):
                raise ValueError(t("El bot no está frenado."))
            self.bot.detener()
            st = PT.load_state(); st["frenado"] = False
            st["ref_limite"] = sum(v["equity"] for v in st["sleeves"].values()) + st.get("libre", 0.0)
            PT.save_state(st); PT.log(t("Bot reanudado después del límite de pérdida, desde la app de control."))
            self.bot.iniciar(); return "ok"
        if a == "laboratorio":
            aj = self.lab.ajustes(); aj["activo"] = bool(d.get("activo"))
            PT.guardar_ajustes(laboratorio=aj)
            PT.log(t("Laboratorio de estrategias encendido.") if aj["activo"] else t("Laboratorio de estrategias apagado."))
            return "ok"
        if a == "buscar_estrategias":
            if not self.lab.lanzar():
                raise ValueError(t("El laboratorio ya está buscando."))
            return "ok"
        if a == "descartar_candidata":
            id_ = str(d.get("id", ""))
            if not id_.startswith("LAB_") or "/" in id_ or "\\" in id_ or ".." in id_:
                raise ValueError("id")
            os.makedirs(os.path.join("candidatas", "descartadas"), exist_ok=True)
            os.replace(os.path.join("candidatas", id_ + ".json"), os.path.join("candidatas", "descartadas", id_ + ".json"))
            return "ok"
        if a == "avisos_leidos":
            import alertas
            alertas.marcar_leidas(d.get("ids")); return "ok"
        if a == "recalcular_historial":
            self.mkt.recalcular.set(); return "ok"
        if a == "buscar_actualizacion":
            return self.buscar_actualizacion(instalar=False)
        if a == "instalar_actualizacion":
            return self.buscar_actualizacion(instalar=True)
        if a == "actualizaciones_auto":
            PT.guardar_ajustes(instalar_actualizaciones_auto=bool(d.get("activo"))); return "ok"
        raise ValueError(t("Acción desconocida: {a}", a=a))


# ------------------------------------------------------------------ API HTTPS
class ServidorTLS(ThreadingHTTPServer):
    """HTTPS donde el saludo TLS se hace en el hilo de cada conexión, con tiempo límite: un cliente que abre el puerto y
    no manda nada (los escáneres de internet lo hacen todo el tiempo) no traba a los demás."""
    daemon_threads = True

    def __init__(self, direccion, manejador, ctx):
        super().__init__(direccion, manejador)
        self.ctx = ctx

    def finish_request(self, request, client_address):
        request.settimeout(20)
        try:
            tls = self.ctx.wrap_socket(request, server_side=True)
        except (ssl.SSLError, OSError):
            return
        try:
            self.RequestHandlerClass(tls, client_address, self)
        finally:
            try:
                tls.close()
            except OSError:
                pass


class Manejador(BaseHTTPRequestHandler):
    timeout = 20
    servicio = None
    token = ""
    fallos = {}  # ip -> (cantidad, hora del último)
    server_version = "bot-trading"
    sys_version = ""

    def log_message(self, fmt, *args):  # sin registro de cada pedido (el registro del bot queda limpio)
        pass

    def _responder(self, codigo, datos):
        cuerpo = json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _autorizado(self):
        ip = self.client_address[0]
        n, cuando = self.fallos.get(ip, (0, 0))
        if n >= 5 and time.time() - cuando < 600:  # 5 intentos fallidos: 10 minutos sin responder a esa IP
            return False
        recibido = self.headers.get("Authorization", "")
        ok = hmac.compare_digest(recibido.encode(), f"Bearer {self.token}".encode())
        if not ok:
            self.fallos[ip] = (n + 1, time.time())
            time.sleep(1)
        else:
            self.fallos.pop(ip, None)
        return ok

    def do_GET(self):
        if not self._autorizado():
            return self._responder(401, {"error": "no autorizado"})
        try:
            ruta = self.path.split("?")[0]
            if ruta == "/api/estado":
                return self._responder(200, self.servicio.estado())
            if ruta.startswith("/api/detalle/"):
                return self._responder(200, self.servicio.detalle(ruta.rsplit("/", 1)[1]))
            return self._responder(404, {"error": "no existe"})
        except KeyError:
            return self._responder(404, {"error": "no existe"})
        except Exception as e:
            PT.log(f"API: {type(e).__name__}: {e}")
            return self._responder(500, {"error": f"{type(e).__name__}"})

    def do_POST(self):
        if not self._autorizado():
            return self._responder(401, {"error": "no autorizado"})
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            if largo > 100_000:
                return self._responder(413, {"error": "demasiado grande"})
            d = json.loads(self.rfile.read(largo) or b"{}")
            if self.path.split("?")[0] != "/api/accion" or not isinstance(d, dict):
                return self._responder(404, {"error": "no existe"})
            return self._responder(200, {"ok": True, "resultado": self.servicio.accion(d)})
        except ValueError as e:
            return self._responder(400, {"error": str(e)})
        except Exception as e:
            PT.log(f"API: {type(e).__name__}: {e}")
            return self._responder(500, {"error": f"{type(e).__name__}"})


def correr():
    c = leer_config()
    if not c.get("token") or not os.path.exists(CERT):
        print("Falta preparar el servidor: python3 servidor.py preparar"); sys.exit(1)
    srv = Servicio()
    srv.arrancar()
    Manejador.servicio, Manejador.token = srv, c["token"]
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(CERT, CLAVE)
    httpd = ServidorTLS(("0.0.0.0", int(c.get("puerto", 8443))), Manejador, ctx)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    PT.log(t("Servidor del bot {v} corriendo (modo {m}); las apps de control se conectan por el puerto {p}.",
             v=K.VERSION, m=t(K.NOMBRE_MODO[K.MODO]), p=c.get("puerto", 8443)))
    try:
        while not srv.salir.is_set():
            srv.salir.wait(5)
    except KeyboardInterrupt:
        pass
    httpd.shutdown()
    srv.bot.detener()
    sys.exit(srv.codigo_salida)


# ------------------------------------------------------------------ comandos de consola
def cmd_preparar(a):
    c = leer_config()
    ip = a.ip or c.get("ip") or ip_publica()
    if not ip:
        print("No pude averiguar la IP pública. Volvé a correrlo con --ip <la IP pública de tu servidor>"); sys.exit(1)
    if c.get("token") and not a.nuevo:
        print("El servidor ya estaba preparado. Para cambiar el token y el certificado (las apps se vuelven a conectar con "
              "el código nuevo), usá: python3 servidor.py preparar --nuevo")
    else:
        c.update(token=secrets.token_urlsafe(32), huella=crear_certificado(ip), ip=ip, puerto=a.puerto)
        guardar_config(c)
        print("Listo: certificado y token creados.")
    print("\nCódigo de conexión para las apps (copialo entero, empieza con BOT1-):\n")
    print(codigo_conexion(leer_config()))
    print("\nGuardalo como una contraseña: con este código se controla el bot.")


def cmd_codigo(a):
    c = leer_config()
    if not c.get("token"):
        print("Primero: python3 servidor.py preparar"); sys.exit(1)
    print(codigo_conexion(c))


def cmd_claves(a):
    import claves as CL
    m = a.modo
    print(f"Claves de API de Binance para {m}. Las claves quedan solo en este servidor (archivo con permisos 600).\n")
    print("1) Ed25519 (recomendado): el servidor genera el par de claves; vos pegás la pública en Binance.")
    print("2) HMAC: pegás la API key y la secret key que te da Binance.")
    op = input("Elegí 1 o 2: ").strip()
    if op == "1":
        par = CL.cargar_privada_pendiente(m)
        if not par:
            priv, pub = CL.generar_ed25519(); CL.guardar_privada_pendiente(m, priv, pub); par = (priv, pub)
        print("\nEn Binance → Gestión de API → Crear API → 'Generada por el usuario' (Ed25519), pegá esta clave pública:\n")
        print(par[1])
        print("Permisos: SOLO futuros (sin retiros). Restringí el acceso a la IP de este servidor: "
              f"{leer_config().get('ip') or ip_publica() or '(tu IP pública)'}\n")
        key = getpass.getpass("Pegá la API key que te muestra Binance (no se ve al escribir): ").strip()
        if not key:
            print("Cancelado."); return
        CL.completar_ed25519(m, key)
    elif op == "2":
        key = getpass.getpass("API key (no se ve al escribir): ").strip()
        sec = getpass.getpass("Secret key (no se ve al escribir): ").strip()
        if not key or not sec:
            print("Cancelado."); return
        CL.guardar(m, key, sec)
    else:
        print("Cancelado."); return
    print(f"Claves guardadas: {CL.enmascarar(CL.cargar(m)[0])}. Ahora probalas: python3 servidor.py probar {m}")


def cmd_probar(a):
    import claves as CL
    import live as LV
    m = a.modo
    cred = CL.cargar(m)
    if not cred:
        print(f"No hay claves de {m}. Cargalas con: python3 servidor.py claves {m}"); sys.exit(1)
    PT.configurar_modo(m)
    try:
        br = LV.Broker(m, *cred)
        s = br.saldo()
        print(f"Conexión OK. Saldo en futuros: libre {s['libre']:.2f} USDT, total {s.get('total', 0):.2f} USDT.")
        PT.guardar_ajustes(**{f"probado_{m}": True})
        if m == "real":
            rs = br.restricciones()
            PT.guardar_ajustes(restricciones_real=dict(rs, hora=time.time()))
            print(f"Permisos: futuros {'sí' if rs['futuros'] else 'NO'}, retiros {'SÍ (deshabilitalos)' if rs['retiros'] else 'no'}, "
                  f"restricción de IP {'sí' if rs['ip'] else 'NO (activala)'}.")
    except Exception as e:
        print(f"No se pudo conectar: {type(e).__name__}: {e}"); sys.exit(1)


def cmd_modo(a):
    import claves as CL
    m = a.modo
    aj = PT.leer_ajustes()
    if m != "simulado" and not (CL.cargar(m) and aj.get(f"probado_{m}")):
        print(f"Primero cargá y probá las claves: python3 servidor.py claves {m} y python3 servidor.py probar {m}")
        sys.exit(1)
    if m == "real":
        rs = aj.get("restricciones_real") or {}
        if not rs or rs.get("retiros") or not rs.get("ip") or not rs.get("futuros"):
            print("La clave real tiene que tener futuros habilitados, retiros deshabilitados y restricción de IP. "
                  "Corregilo en Binance y volvé a probar: python3 servidor.py probar real"); sys.exit(1)
        cap = aj.get("capital", {}).get("real", 100)
        print(f"Vas a operar con DINERO REAL: hasta {cap} USDT, {K.RISK_PER_TRADE * 100:.1f} % de riesgo por operación. "
              "Podés perder dinero.")
        if input("Escribí REAL para confirmar: ").strip() != "REAL":
            print("Cancelado."); return
    PT.guardar_ajustes(modo=m)
    print(f"Modo guardado: {m}. Reiniciá el servicio para aplicarlo: sudo systemctl restart bot-trading")


def cmd_estado(a):
    import app_data as A
    PT.configurar_modo(PT.leer_ajustes().get("modo", "simulado"))
    s = A.snapshot(".")
    print(f"Versión {K.VERSION} · modo {K.MODO} · saldo {s['saldo']:.2f} USDT · posiciones abiertas {len(s['abiertas'])}")


def cmd_probar_push(a):
    import push
    if not push.configurado():
        print(f"Falta {push.ARCH_CLAVE} en {os.getcwd()}: copiá ahí la clave de la cuenta de servicio de Firebase.")
        return
    fb = push.Firebase()
    try:
        fb._acceso()
    except Exception as e:
        print(f"No se pudo autenticar con Firebase: {type(e).__name__}: {e}"); return
    print(f"Firebase OK (proyecto {fb.proyecto}). Celulares registrados: {len(push.tokens())}.")
    if not push.tokens():
        print("Abrí la app del celular (versión nueva) para que se registre y volvé a probar."); return
    ok, err = push.enviar_a_todos(fb, "Prueba de avisos", "Si ves esto, los avisos del bot llegan al celular.")
    print(f"Enviados: {ok}." + (f" Errores: {err}" if err else ""))


def main():
    ap = argparse.ArgumentParser(description="Bot de trading en un servidor")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("preparar"); p.add_argument("--ip"); p.add_argument("--puerto", type=int, default=8443)
    p.add_argument("--nuevo", action="store_true")
    sub.add_parser("codigo")
    for nombre in ("claves", "probar"):
        p = sub.add_parser(nombre); p.add_argument("modo", choices=["demo", "real"])
    p = sub.add_parser("modo"); p.add_argument("modo", choices=["simulado", "demo", "real"])
    sub.add_parser("estado"); sub.add_parser("correr"); sub.add_parser("probar_push")
    a = ap.parse_args()
    try:
        {"preparar": cmd_preparar, "codigo": cmd_codigo, "claves": cmd_claves, "probar": cmd_probar, "modo": cmd_modo,
         "estado": cmd_estado, "correr": lambda a: correr(), "probar_push": cmd_probar_push,
         None: lambda a: ap.print_help()}[a.cmd](a)
    except KeyboardInterrupt:
        print("\nCancelado.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)
