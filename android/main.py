"""Bot de trading — control remoto para Android.

Se conecta al bot que corre en el servidor (Oracle Cloud) con el código de conexión (BOT1-...), por HTTPS con el
certificado del servidor fijado. Muestra el estado, las posiciones, las operaciones y los avisos, y deja prender o apagar
el bot, el piloto y el laboratorio, revisar ahora, reanudar después del límite de pérdida y cambiar el riesgo y el capital.
La app no necesita quedar abierta: el bot corre en el servidor.
"""
import json
import os
import threading
import time
from datetime import datetime

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.switch import Switch
from kivy.uix.textinput import TextInput
from kivy.utils import get_color_from_hex as hexc, platform

import cliente_api as C


FONDO, PANEL, TEXTO, GRIS = hexc("#0f1115"), hexc("#181b22"), hexc("#e8eaf0"), hexc("#8b90a0")
VERDE, ROJO, AMBAR, ACENTO = hexc("#2fbf71"), hexc("#e5484d"), hexc("#f5a524"), hexc("#f08a24")
Window.clearcolor = FONDO
PIL_BASE = ("BREAKOUT", "TL")


def num(v, d=2, signo=False):
    if v is None:
        return "—"
    s = f"{abs(v):,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("+" if signo and v > 0 else "-" if v < 0 else "") + s


def usd(v, d=2, signo=False):
    return f"{num(v, d, signo)} USDT"


def pct(v, d=1, signo=False):
    return f"{num(v, d, signo)} %"


def color(v):
    return GRIS if v is None else (VERDE if v > 0 else ROJO if v < 0 else TEXTO)


class Texto(Label):
    def __init__(self, texto="", tam=15, col=TEXTO, negrita=False, **kw):
        super().__init__(text=texto, font_size=sp(tam), color=col, bold=negrita, halign="left", valign="middle",
                         size_hint_y=None, **kw)
        self.bind(width=lambda *_: setattr(self, "text_size", (self.width, None)))
        self.bind(texture_size=lambda *_: setattr(self, "height", self.texture_size[1] + dp(6)))


class Boton(Button):
    def __init__(self, texto, accion, col=PANEL, **kw):
        super().__init__(text=texto, font_size=sp(15), size_hint_y=None, height=dp(48), background_normal="",
                         background_color=col, color=TEXTO, **kw)
        self.bind(on_release=lambda *_: accion())


class Tarjeta(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", size_hint_y=None, padding=dp(14), spacing=dp(6), **kw)
        self.bind(minimum_height=self.setter("height"))
        from kivy.graphics import Color, RoundedRectangle
        with self.canvas.before:
            Color(*PANEL)
            self._r = RoundedRectangle(radius=[dp(12)])
        self.bind(pos=lambda *_: setattr(self._r, "pos", self.pos), size=lambda *_: setattr(self._r, "size", self.size))


def pagina():
    sv = ScrollView(do_scroll_x=False)
    caja = BoxLayout(orientation="vertical", size_hint_y=None, padding=dp(12), spacing=dp(12))
    caja.bind(minimum_height=caja.setter("height"))
    sv.add_widget(caja)
    return sv, caja


def preguntar(titulo, texto, si, accion, al_cancelar=None):
    caja = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(12))
    caja.add_widget(Texto(texto))
    fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
    pop = Popup(title=titulo, content=caja, size_hint=(0.92, None), height=dp(300), auto_dismiss=False)
    fila.add_widget(Boton("Cancelar", lambda: (pop.dismiss(), al_cancelar and al_cancelar())))
    fila.add_widget(Boton(si, lambda: (pop.dismiss(), accion()), col=ACENTO))
    caja.add_widget(fila)
    pop.open()


def avisar(titulo, texto):
    caja = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(12))
    caja.add_widget(Texto(texto))
    pop = Popup(title=titulo, content=caja, size_hint=(0.92, None), height=dp(280))
    caja.add_widget(Boton("OK", pop.dismiss, col=ACENTO))
    pop.open()


class ControlApp(App):
    title = "Bot de trading"

    def on_pause(self):
        self.en_frente = False  # con la app cerrada o en segundo plano, los avisos llegan por push (Firebase)
        return True  # al salir de la app, Android la deja en pausa en lugar de cerrarla

    def on_resume(self):
        self._primer_vistazo = True  # lo que pasó mientras estaba cerrada ya llegó por push: no repetirlo
        self.en_frente = True
        if getattr(self, "cliente", None) and getattr(self, "datos", None):
            Clock.schedule_once(lambda dt: self._pintar(), 0.3)

    def build(self):
        self.archivo = os.path.join(self.user_data_dir, "codigo.json")
        self.cliente, self.datos, self.error, self.pestana = None, None, None, "resumen"
        self.en_frente, self._primer_vistazo = True, True
        self.raiz = BoxLayout(orientation="vertical")
        cod = self._leer_codigo()
        if cod:
            self._conectar(cod)
        else:
            self._pantalla_codigo()
        return self.raiz

    # ---------- código de conexión (en el almacenamiento privado de la app)
    def _leer_codigo(self):
        try:
            with open(self.archivo, encoding="utf-8") as f:
                return json.load(f)["codigo"]
        except (OSError, ValueError, KeyError):
            return None

    def _guardar_codigo(self, cod):
        with open(self.archivo, "w", encoding="utf-8") as f:
            json.dump({"codigo": cod}, f)

    def _pantalla_codigo(self, error=""):
        self.raiz.clear_widgets()
        sv, caja = pagina()
        caja.add_widget(Texto("Conectar con el servidor", 22, negrita=True))
        caja.add_widget(Texto("Pegá el código de conexión del servidor (empieza con BOT1-). Lo muestra el servidor al "
                              "instalarlo, o con: venv/bin/python servidor.py codigo", 14, GRIS))
        if error:
            caja.add_widget(Texto(error, 14, ROJO))
        entrada = TextInput(multiline=True, size_hint_y=None, height=dp(140), font_size=sp(14),
                            background_color=PANEL, foreground_color=TEXTO)
        caja.add_widget(entrada)

        def pegar():  # en Android, mantener apretado el campo no siempre muestra "Pegar"
            try:
                from kivy.core.clipboard import Clipboard
                txt = Clipboard.paste() or ""
            except Exception:
                txt = ""
            if not txt.strip():
                return avisar("Pegar", "No hay nada copiado. Copiá el código completo (empieza con BOT1-) y volvé a "
                                       "tocar Pegar.")
            entrada.text = txt.strip()
        caja.add_widget(Boton("Pegar el código copiado", pegar))

        def conectar():
            cod = "".join(entrada.text.split())
            try:
                C.leer_codigo(cod)
            except ValueError as e:
                return self._pantalla_codigo(str(e))
            self._guardar_codigo(cod)
            self._conectar(cod)
        caja.add_widget(Boton("Conectar", conectar, col=ACENTO))
        self.raiz.add_widget(sv)

    def _conectar(self, cod):
        try:
            self.cliente = C.Cliente(cod)
        except ValueError as e:
            return self._pantalla_codigo(str(e))
        self._armar()
        if not getattr(self, "_sondeando", False):
            self._sondeando = True
            threading.Thread(target=self._sondeo, daemon=True).start()
        if self._avisos_activos():
            self._activar_push()

    # ---------- notificaciones de operaciones: push de Firebase (llegan con la app cerrada, como Instagram)
    def _avisos_activos(self):
        try:
            with open(os.path.join(self.user_data_dir, "avisos_ajustes.json"), encoding="utf-8") as f:
                return bool(json.load(f).get("activo", True))
        except (OSError, ValueError):
            return True

    def _guardar_avisos(self, activo):
        with open(os.path.join(self.user_data_dir, "avisos_ajustes.json"), "w", encoding="utf-8") as f:
            json.dump({"activo": bool(activo)}, f)

    def _activar_push(self):
        """Pide permiso de notificaciones, crea el canal y registra este celular en el servidor."""
        if platform != "android":
            return
        try:
            import notificaciones as N
            N.pedir_permiso()
            N.crear_canal()
            N.pedir_token(self._token_listo)
        except Exception as e:
            self.estado_push = f"No se pudieron activar: {type(e).__name__}: {e}"[:200]

    def _token_listo(self, token, error):
        if error or not token:
            self.estado_push = f"Firebase no dio el token: {error}"[:200]
            return
        self.token_push = token

        def registrar():
            try:
                r = self.cliente.accion("push_registrar", token=token, version=self._version_app())
                self.estado_push = "ok" if r == "ok" else "falta_servidor"
            except Exception as e:
                self.estado_push = f"No se pudo registrar en el servidor: {e}"[:200]
        threading.Thread(target=registrar, daemon=True).start()

    def _desactivar_push(self):
        tk = getattr(self, "token_push", None)
        if tk:
            threading.Thread(target=lambda: self.cliente.accion("push_quitar", token=tk), daemon=True).start()
        self.estado_push = "apagado"

    def _avisos_en_frente(self):
        """Con la app abierta, Android no muestra los push: la app avisa ella misma de lo nuevo."""
        if platform != "android" or not self._avisos_activos():
            return
        import avisos as AV
        vistos = os.path.join(self.user_data_dir, "avisos_vistos_app.json")
        ev = self.cliente.detalle("eventos")
        if self._primer_vistazo or not self.en_frente:
            AV.nuevos(ev.get("eventos") or [], vistos)  # solo marca
            self._primer_vistazo = False
            return
        import notificaciones as N
        for e in AV.nuevos(ev.get("eventos") or [], vistos):
            titulo, cuerpo = AV.texto(e, ev.get("nombre_modo") or "")
            N.notificar(e["id"], titulo, cuerpo)

    # ---------- versión nueva de la app (cada versión del servidor trae su APK)
    def _version_app(self):
        if platform != "android":
            return None
        try:
            from jnius import autoclass
            act = autoclass("org.kivy.android.PythonActivity").mActivity
            return act.getPackageManager().getPackageInfo(act.getPackageName(), 0).versionName
        except Exception:
            return None

    def _bajar_version(self):
        import avisos as AV
        if platform != "android":
            import webbrowser
            return webbrowser.open(AV.URL_APK)
        from jnius import autoclass
        Intent, Uri = autoclass("android.content.Intent"), autoclass("android.net.Uri")
        autoclass("org.kivy.android.PythonActivity").mActivity.startActivity(Intent(Intent.ACTION_VIEW,
                                                                                    Uri.parse(AV.URL_APK)))

    def _tarjeta_version(self, d, caja):
        import avisos as AV
        if not hasattr(self, "version_app"):
            self.version_app = self._version_app()
        if not AV.version_nueva(d.get("version"), self.version_app):
            return
        t = Tarjeta()
        t.add_widget(Texto(f"Hay una versión nueva de la app: {d.get('version')} (tenés la {self.version_app}).", 15,
                           AMBAR, negrita=True))
        t.add_widget(Texto("Tocá el botón, esperá que baje, abrí el archivo y tocá Actualizar. Android siempre pide "
                           "confirmar la instalación. Tus datos y el código de conexión se conservan.", 13, GRIS))
        t.add_widget(Boton("Bajar la versión nueva", self._bajar_version, col=ACENTO))
        caja.add_widget(t)

    def _cambiar_avisos(self, activo):
        self._guardar_avisos(activo)
        if activo:
            self._activar_push()
        else:
            self._desactivar_push()

    # ---------- estructura: contenido + barra de pestañas abajo
    def _armar(self):
        self.raiz.clear_widgets()
        self.cabecera = Texto("Conectando…", 13, GRIS, padding=(dp(12), dp(6)))
        self.raiz.add_widget(self.cabecera)
        self.cuerpo = BoxLayout()
        self.raiz.add_widget(self.cuerpo)
        # 7 pestañas no entran en el ancho de un celular: la barra se desliza de costado
        desliza = ScrollView(size_hint_y=None, height=dp(56), do_scroll_y=False, bar_width=0)
        barra = BoxLayout(size_hint_x=None, spacing=dp(2))
        barra.bind(minimum_width=barra.setter("width"))
        self.tabs = {}
        for k, n in (("resumen", "Resumen"), ("posiciones", "Posiciones"), ("operaciones", "Operaciones"),
                     ("estrategias", "Estrategias"), ("decisiones", "Decisiones"), ("avisos", "Avisos"),
                     ("control", "Control"), ("servidor", "Servidor")):
            b = Button(text=n, font_size=sp(13), background_normal="", background_color=PANEL, color=TEXTO,
                       size_hint_x=None, width=dp(104))
            b.bind(on_release=lambda _b, k=k: self._ir(k))
            barra.add_widget(b); self.tabs[k] = b
        desliza.add_widget(barra)
        self.raiz.add_widget(desliza)
        self._ir("resumen")

    def _ir(self, k):
        self.pestana = k
        if k == "decisiones":
            self.rev_idx = 0
            threading.Thread(target=self._traer_decisiones, daemon=True).start()
        for kk, b in self.tabs.items():
            b.color = ACENTO if kk == k else TEXTO
        self._pintar()

    # ---------- datos
    def _traer_decisiones(self):
        try:
            self.decisiones = self.cliente.detalle("decisiones").get("decisiones") or []
        except Exception as e:
            self.error = str(e)
        self._pintar()

    def _sondeo(self):
        while True:
            try:
                d = self.cliente.estado()
                self.datos, self.error = d, None
                if getattr(self, "pestana", "") == "decisiones":
                    self.decisiones = self.cliente.detalle("decisiones").get("decisiones") or []
                self._avisos_en_frente()
            except (C.ErrorConexion, C.ErrorServidor) as e:
                self.error = str(e)
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"
            self._pintar(desde_sondeo=True)
            time.sleep(10)

    def _accion(self, nombre, ok="", **datos):
        def tarea():
            try:
                self.cliente.accion(nombre, **datos)
                if ok:
                    self._avisar("Servidor", ok)
                self.datos = self.cliente.estado()
            except (C.ErrorConexion, C.ErrorServidor) as e:
                self._avisar("Servidor", str(e))
            self._pintar()
        threading.Thread(target=tarea, daemon=True).start()

    @mainthread
    def _avisar(self, titulo, texto):
        avisar(titulo, texto)

    # ---------- pantallas
    @mainthread
    def _pintar(self, *_, desde_sondeo=False):
        if not hasattr(self, "cuerpo"):
            return
        d = self.datos
        if self.error:
            self.cabecera.text = "Sin conexión: " + self.error[:140]
            self.cabecera.color = ROJO
        elif d:
            b = d["bot"]
            estado = "Frenado" if d["snap"].get("frenado") else ("Corriendo" if b.get("corriendo") else "Detenido")
            prox = (f" · próxima revisión {datetime.fromtimestamp(b['proxima_revision']):%H:%M}"
                    if b.get("proxima_revision") else "")
            self.cabecera.text = f"{estado} · {d.get('nombre_modo', '')} · servidor {d.get('version', '')}{prox}"
            self.cabecera.color = ROJO if d["snap"].get("frenado") else (VERDE if b.get("corriendo") else AMBAR)
        if desde_sondeo and self.pestana in ("control", "servidor") and self.cuerpo.children:
            return  # no rehace estas pantallas mientras escribís (se actualizan al entrar o al hacer una acción)
        self.cuerpo.clear_widgets()
        if not d:
            sv, caja = pagina(); caja.add_widget(Texto("Esperando datos del servidor…", 15, GRIS))
            self.cuerpo.add_widget(sv); return
        getattr(self, "_p_" + self.pestana)(d)
        sl = d.get("sin_leer") or 0
        self.tabs["avisos"].text = f"Avisos ({sl})" if sl else "Avisos"

    def _p_resumen(self, d):
        s = d["snap"]
        sv, caja = pagina()
        self._tarjeta_version(d, caja)
        t = Tarjeta()
        t.add_widget(Texto("Saldo del bot", 13, GRIS))
        t.add_widget(Texto(usd(s["saldo"]), 30, negrita=True))
        t.add_widget(Texto(f"{pct(s['rendimiento_pct'], 2, True)} sobre {usd(s['base'])}", 14, color(s["rendimiento_pct"])))
        g = GridLayout(cols=2, size_hint_y=None, spacing=dp(6)); g.bind(minimum_height=g.setter("height"))
        for tit, v, c in (("Resultado cerrado", usd(s["realizado"], 2, True), color(s["realizado"])),
                          ("Resultado abierto", usd(s["abierto"], 2, True), color(s["abierto"])),
                          ("Sin asignar", usd(s["libre"]), TEXTO),
                          ("Operaciones", str(s["resumen_ops"]["n"]), TEXTO)):
            g.add_widget(Texto(tit, 13, GRIS)); g.add_widget(Texto(v, 15, c, negrita=True))
        t.add_widget(g)
        caja.add_widget(t)
        t = Tarjeta(); t.add_widget(Texto("Mercado ahora", 17, negrita=True))
        g = GridLayout(cols=3, size_hint_y=None, spacing=dp(6)); g.bind(minimum_height=g.setter("height"))
        for a in ("BTC", "ETH", "SOL"):
            x = (s.get("precios") or {}).get(a) or {}
            px, ch = x.get("precio"), x.get("cambio")
            g.add_widget(Texto(a, 15, negrita=True))
            g.add_widget(Texto(num(px, 2 if (px or 0) >= 100 else 4), 15))
            g.add_widget(Texto(f"{pct(ch, 1, True)} en 24 h" if ch is not None else "", 13, color(ch)))
        t.add_widget(g)
        if d.get("precios_hora"):
            seg = max(0, int(time.time() - d["precios_hora"]))
            t.add_widget(Texto(f"Binance Futuros, hace {seg} s" if seg < 120 else f"Binance Futuros, hace {seg // 60} min",
                               12, GRIS))
        caja.add_widget(t)
        if s.get("frenado"):
            f = Tarjeta()
            f.add_widget(Texto("El bot está frenado por el límite de pérdida: no abre operaciones nuevas.", 14, AMBAR))
            f.add_widget(Boton("Reanudar", lambda: preguntar("Reanudar", "¿Permitir que el bot vuelva a abrir "
                                                             "operaciones? El límite se mide desde el saldo actual.",
                                                             "Reanudar", lambda: self._accion("reanudar")), col=ACENTO))
            caja.add_widget(f)
        ab = s.get("abiertas") or []
        t = Tarjeta(); t.add_widget(Texto("Posiciones abiertas", 17, negrita=True))
        for f in ab:
            t.add_widget(Texto(f"{f['activo']} {f['estrategia']}: {'compra' if f['lado'] == 'long' else 'venta'} · "
                               f"{usd(f.get('pnl'), 2, True)}", 14, color(f.get("pnl"))))
        if not ab:
            t.add_widget(Texto("Sin posiciones abiertas. El bot entra cuando aparece una señal.", 14, GRIS))
        caja.add_widget(t)
        meses, _dd = s.get("mensual") or ([], 0)
        hist = (d.get("historial") or {}).get("estrategias") or {}
        base = [b for b in PIL_BASE if b in hist]
        hoy = datetime.now().strftime("%Y-%m")
        t = Tarjeta(); t.add_widget(Texto("Resultados por mes (bot · simulación)", 17, negrita=True))
        for x in list(reversed(meses))[:12]:
            vals = [(hist[b].get("mensual") or {}).get(x["mes"]) for b in base]
            sim = sum(vals) / len(vals) if base and x["mes"] < hoy and all(v is not None for v in vals) else None
            t.add_widget(Texto(f"{x['mes'][5:]}/{x['mes'][:4]}:  bot {pct(x.get('pct'), 1, True)}  ·  simulación "
                               f"{pct(sim, 1, True)}", 14, color(x.get("pct"))))
        if not meses:
            t.add_widget(Texto("Todavía no hay meses.", 14, GRIS))
        caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _p_posiciones(self, d):
        sv, caja = pagina()
        for f in d["snap"]["posiciones"]:
            t = Tarjeta()
            t.add_widget(Texto(f"{f['activo']} · {f['estrategia']}", 16, negrita=True))
            t.add_widget(Texto(f"Monto {usd(f['asignado'])} · capital {usd(f['capital'])}", 14, GRIS))
            if f["lado"]:
                t.add_widget(Texto(f"{'Compra' if f['lado'] == 'long' else 'Venta'} a {num(f['entrada'])} · stop "
                                   f"{num(f['stop'])} · {usd(f.get('pnl'), 2, True)}", 14, color(f.get("pnl"))))
            else:
                t.add_widget(Texto("Sin posición abierta", 14, GRIS))
            caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _p_operaciones(self, d):
        sv, caja = pagina()
        r = d["snap"]["resumen_ops"]
        caja.add_widget(Texto(f"{r['n']} operaciones, {r['ganadas']} ganadoras. Resultado {usd(r['pnl'], 2, True)}.",
                              14, GRIS))
        for o in d["snap"].get("ultimas_operaciones") or []:
            t = Tarjeta()
            t.add_widget(Texto(f"{o.get('activo')} · {o.get('estrategia')} · {'compra' if o.get('lado') == 'long' else 'venta'}",
                               15, negrita=True))
            t.add_widget(Texto(f"{str(o.get('salida_t', ''))[:16]} · {o.get('motivo', '')}", 13, GRIS))
            t.add_widget(Texto(usd(o.get("pnl"), 2, True), 15, color(o.get("pnl"))))
            caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _p_avisos(self, d):
        sv, caja = pagina()
        caja.add_widget(Boton("Marcar todos como leídos", lambda: self._accion("avisos_leidos")))
        for a in d.get("alertas") or []:
            t = Tarjeta()
            t.add_widget(Texto(a["titulo"], 15, negrita=not a.get("leida")))
            t.add_widget(Texto(f"{datetime.fromtimestamp(a['hora']):%d/%m %H:%M}", 12, GRIS))
            t.add_widget(Texto(a.get("texto", ""), 14))
            caja.add_widget(t)
        if not d.get("alertas"):
            caja.add_widget(Texto("No hay avisos.", 14, GRIS))
        self.cuerpo.add_widget(sv)

    def _p_decisiones(self, d):
        sv, caja = pagina()
        caja.add_widget(Texto("Qué miró el bot en cada revisión, para cada estrategia en cada moneda: qué condiciones se "
                              "cumplen (en verde) y cuáles faltan (en rojo) para abrir.", 13, GRIS))
        dec = getattr(self, "decisiones", None)
        if dec is None:
            caja.add_widget(Texto("Cargando…", 15, GRIS)); self.cuerpo.add_widget(sv); return
        if not dec:
            caja.add_widget(Texto("Todavía no hay revisiones registradas. La primera aparece después de la próxima "
                                  "revisión del bot.", 15, GRIS))
            self.cuerpo.add_widget(sv); return
        i = min(getattr(self, "rev_idx", 0), len(dec) - 1)
        x = dec[i]
        h = datetime.fromisoformat(x["hora"])
        fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))

        def mover(paso):
            self.rev_idx = max(0, min(len(dec) - 1, i + paso)); self._pintar()
        fila.add_widget(Boton("< Anterior", lambda: mover(1)))
        fila.add_widget(Boton("Siguiente >", lambda: mover(-1)))
        caja.add_widget(fila)
        caja.add_widget(Texto(f"Revisión del {h:%d/%m %H:%M}, vela de {x['vela']}" + (" (la última)" if i == 0 else ""),
                              15, negrita=True))
        ab = sum(1 for it in x["items"] if it["accion"] == "abre")
        ce = sum(1 for it in x["items"] if it["accion"] == "cierra")
        caja.add_widget(Texto(f"Abrió {ab} y cerró {ce} posiciones. Revisó {len(x['items'])} partes del capital.", 13))
        acciones = {"abre": ("Abre", VERDE), "cierra": ("Cierra", ACENTO), "mantiene": ("Mantiene", AMBAR),
                    "no_abre": ("No abre", GRIS), "inactiva": ("Desactivada", GRIS)}
        for it in x["items"]:
            t = Tarjeta()
            txt, col = acciones.get(it["accion"], (it["accion"], GRIS))
            t.add_widget(Texto(f"{it['activo']} · {it.get('estrategia', '')}", 15, negrita=True))
            t.add_widget(Texto(txt, 14, col, negrita=True))
            conds = it.get("condiciones") or []
            if it["accion"] == "no_abre" and conds:
                t.add_widget(Texto(f"Se cumplen {sum(1 for _, ok in conds if ok)} de {len(conds)} condiciones para "
                                   "entrar:", 13))
            elif it["accion"] == "no_abre":
                t.add_widget(Texto("No hubo señal de entrada.", 13, GRIS))
            elif it.get("texto"):
                t.add_widget(Texto(it["texto"][0].upper() + it["texto"][1:] + ".", 13))
            for ctext, ok in conds:
                t.add_widget(Texto(("Sí · " if ok else "No · ") + ctext, 13, VERDE if ok else ROJO))
            caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _fila_switch(self, caja, texto, activo, al_cambiar):
        fila = BoxLayout(size_hint_y=None, height=dp(48))
        fila.add_widget(Texto(texto, 15))
        sw = Switch(active=bool(activo), size_hint_x=None, width=dp(90))
        sw.bind(active=lambda _s, v: al_cambiar(v))
        fila.add_widget(sw)
        caja.add_widget(fila)

    def _p_control(self, d):
        b = d["bot"]
        sv, caja = pagina()
        t = Tarjeta(); t.add_widget(Texto("Bot", 17, negrita=True))
        if b.get("corriendo"):
            t.add_widget(Boton("Revisar ahora", lambda: self._accion("revisar", "El bot revisa ahora.")))
            t.add_widget(Boton("Detener bot", lambda: preguntar("Detener bot", "¿Detener el bot? Las posiciones abiertas "
                                                                "quedan con su stop en Binance.", "Detener",
                                                                lambda: self._accion("detener")), col=ROJO))
        else:
            t.add_widget(Boton("Iniciar bot", lambda: self._accion("iniciar"), col=ACENTO))
        caja.add_widget(t)
        t = Tarjeta(); t.add_widget(Texto("Notificaciones", 17, negrita=True))
        t.add_widget(Texto("Te avisa en el celular cada vez que el bot abre o cierra una operación, aunque la app esté "
                           "cerrada y la pantalla apagada. Los avisos los manda el servidor por Firebase (el mismo "
                           "sistema de Google que usan Instagram o WhatsApp).", 13, GRIS))
        self._fila_switch(t, "Avisar operaciones", self._avisos_activos(), self._cambiar_avisos)
        ep = getattr(self, "estado_push", None)
        srv = d.get("push") or {}
        if not self._avisos_activos():
            pass
        elif ep == "ok" and srv.get("configurado"):
            t.add_widget(Texto("Avisos encendidos: este celular está registrado en el servidor.", 13, VERDE))
        elif ep == "falta_servidor" or (srv and not srv.get("configurado")):
            t.add_widget(Texto("El celular está listo, pero al servidor le falta la clave de Firebase "
                               "(firebase-servidor.json). Hasta que la tenga, los avisos llegan solo con la app abierta.",
                               13, AMBAR))
        elif ep and ep not in ("ok", "apagado"):
            t.add_widget(Texto(ep, 13, ROJO))
        else:
            t.add_widget(Texto("Registrando este celular…", 13, GRIS))
        caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _tarjeta_capital_minimo(self, d, caja):
        cm = d.get("capital_minimo")
        if not cm:
            return
        alcanza = (cm.get("disponible") or 0) >= cm["total"]
        t = Tarjeta()
        t.add_widget(Texto(f"Capital mínimo recomendado: {usd(cm['total'], 0)} en total", 15,
                           VERDE if alcanza else AMBAR, negrita=True))
        nombre = (d.get("nombres") or {}).get(cm["estrategia"], cm["estrategia"])
        t.add_widget(Texto(f"Son {cm['partes']} partes de {usd(cm['por_parte'], 0)} cada una (lo que más pide hoy Binance "
                           f"es {nombre} en {cm['activo']}, más un 25 % de margen).", 13, GRIS))
        t.add_widget(Texto(f"El bot tiene {usd(cm.get('disponible'), 0)}: "
                           + ("alcanza." if alcanza else "no alcanza para todas las partes."), 13,
                           VERDE if alcanza else AMBAR))
        caja.add_widget(t)

    def _p_estrategias(self, d):
        s = d["snap"]
        au = s.get("auto_estado") or {}
        nombres = d.get("nombres") or {}
        sv, caja = pagina()
        t = Tarjeta(); t.add_widget(Texto("Piloto automático", 17, negrita=True))
        t.add_widget(Texto("Con el piloto encendido el bot usa Breakout y Resorte de tendencia en BTC, ETH y SOL, reparte "
                           "todo el capital en partes iguales una vez por día y revisa una vez por mes que cada una siga "
                           "ganando. Si el laboratorio encuentra una que les gana durante 3 meses de observación, la suma.",
                           13, GRIS))
        self._fila_switch(t, "Encendido", s.get("auto"), lambda v: preguntar(
            "Piloto automático", "¿Encender el piloto?" if v else "¿Apagar el piloto?", "Sí",
            lambda: self._accion("piloto", activo=v), al_cancelar=self._pintar) if bool(v) != bool(s.get("auto")) else None)
        if s.get("auto"):
            dentro = au.get("dentro") or d.get("piloto_base") or []
            t.add_widget(Texto("En uso: " + (", ".join(nombres.get(x, x) for x in dentro) or "ninguna") + ".", 14))
            asig = au.get("asig") or {}
            if asig:
                t.add_widget(Texto(f"{len(asig)} partes de {usd(next(iter(asig.values())))} cada una.", 14))
            for x in dentro:
                sem = (((au.get("revision") or {}).get(x) or {}).get("semestres")) or []
                if len(sem) >= 2:
                    ua = ((1 + sem[0] / 100) * (1 + sem[1] / 100) - 1) * 100
                    t.add_widget(Texto(f"{nombres.get(x, x)}: últimos 12 meses {pct(ua, 1, True)}; fallas seguidas "
                                       f"{(au.get('racha') or {}).get(x, 0)} de {d.get('meses_histeresis', 3)}.", 13))
        else:
            t.add_widget(Texto("Piloto apagado: el bot usa las estrategias y montos elegidos a mano.", 14, AMBAR))
        caja.add_widget(t)
        self._tarjeta_capital_minimo(d, caja)
        caja.add_widget(Texto("Estrategias", 17, negrita=True))
        caja.add_widget(Texto("Resultado de cada año y de los últimos 4 semestres con la estrategia siempre prendida, en "
                              "promedio de BTC, ETH y SOL.", 13, GRIS))
        hist = (d.get("historial") or {}).get("estrategias") or {}
        base_piloto = d.get("piloto_base") or []
        for k, x in hist.items():
            if k in (d.get("retiradas") or []):
                continue
            t = Tarjeta()
            t.add_widget(Texto(nombres.get(k, k), 16, negrita=True))
            t.add_widget(Texto("Base del piloto" if k in PIL_BASE else ("En el piloto (del laboratorio)" if k in base_piloto
                                                                       else "Del laboratorio"), 12,
                               ACENTO if k in base_piloto else AMBAR))
            sem = x.get("semestres") or []
            if len(sem) < 4:
                t.add_widget(Texto("Historial insuficiente para la revisión mensual.", 13, GRIS))
            else:
                ua = ((1 + sem[0] / 100) * (1 + sem[1] / 100) - 1) * 100
                t.add_widget(Texto(f"{'Ganó' if ua > 0 else 'Perdió'} {pct(abs(ua), 1)} en los últimos 12 meses: "
                                   f"{'pasa' if ua > 0 else 'no pasa'} la revisión.", 13, VERDE if ua > 0 else ROJO))
            g = GridLayout(cols=2, size_hint_y=None, spacing=dp(4)); g.bind(minimum_height=g.setter("height"))
            for y in range(2022, datetime.now().year + 1):
                v = (x.get("anios") or {}).get(str(y))
                g.add_widget(Texto(str(y), 13, GRIS)); g.add_widget(Texto(pct(v, 0, True), 14, color(v)))
            g.add_widget(Texto("Últimos 4 semestres", 13, GRIS))
            g.add_widget(Texto("  ·  ".join(pct(v, 0, True) for v in sem) or "—", 14))
            t.add_widget(g)
            caja.add_widget(t)
        if not hist:
            caja.add_widget(Texto("El servidor todavía está calculando el historial de las estrategias.", 14, GRIS))
        self.cuerpo.add_widget(sv)

    def _p_servidor(self, d):
        sv, caja = pagina()
        cl = d.get("claves") or {}
        t = Tarjeta(); t.add_widget(Texto("Conexión", 17, negrita=True))
        t.add_widget(Texto(f"Conectado a {self.cliente.host}:{self.cliente.puerto}. Servidor versión {d.get('version')}, "
                           f"modo {d.get('nombre_modo')}. Claves cargadas: demo {'sí' if cl.get('demo') else 'no'}, real "
                           f"{'sí' if cl.get('real') else 'no'}.", 13))
        t.add_widget(Texto("Las claves de Binance y el modo se cambian en el servidor, por seguridad.", 12, GRIS))
        t.add_widget(Boton("Cambiar código de conexión", lambda: self._pantalla_codigo()))
        caja.add_widget(t)

        t = Tarjeta(); t.add_widget(Texto("Riesgo", 17, negrita=True))
        t.add_widget(Texto("Riesgo por operación, límite de pérdida (frena el bot si la cuenta pierde ese porcentaje del "
                           "capital del modo) y espera de la orden límite antes de completarla a mercado.", 13, GRIS))
        r = d["riesgo"]
        e1 = TextInput(text=num(r["por_operacion"] * 100, 1), multiline=False, input_filter="float", size_hint_y=None,
                       height=dp(44), font_size=sp(15))
        e2 = TextInput(text=str(int(round(r["limite_perdida"] * 100))), multiline=False, input_filter="int",
                       size_hint_y=None, height=dp(44), font_size=sp(15))
        e4 = TextInput(text=str(int(r.get("espera_limite") or 180)), multiline=False, input_filter="int",
                       size_hint_y=None, height=dp(44), font_size=sp(15))
        t.add_widget(Texto("Riesgo por operación (%)", 13, GRIS)); t.add_widget(e1)
        t.add_widget(Texto("Límite de pérdida (%)", 13, GRIS)); t.add_widget(e2)
        t.add_widget(Texto("Espera de la orden límite (segundos)", 13, GRIS)); t.add_widget(e4)

        def guardar_riesgo():
            try:
                po, lp = float(e1.text.replace(",", ".")) / 100, float(e2.text) / 100
                es = int(e4.text)
            except ValueError:
                return avisar("Riesgo", "Revisá los números.")
            self._accion("riesgo", "Riesgo guardado.", por_operacion=po, limite_perdida=lp, espera_limite=es)
        t.add_widget(Boton("Guardar riesgo", guardar_riesgo, col=ACENTO))
        caja.add_widget(t)

        t = Tarjeta(); t.add_widget(Texto("Capital del modo", 17, negrita=True))
        t.add_widget(Texto("Cuánto dinero de la cuenta usa el bot en el modo actual. Con el piloto encendido, el bot "
                           "reparte el cambio solo.", 13, GRIS))
        e3 = TextInput(text=num((d.get("capital") or {}).get(d["modo"], 100), 2).replace(".", ""), multiline=False,
                       input_filter="float", size_hint_y=None, height=dp(44), font_size=sp(15))
        t.add_widget(e3)
        t.add_widget(Boton("Guardar capital", lambda: self._accion("capital", "Capital guardado.",
                                                                    valor=float(e3.text.replace(",", ".") or 0)),
                           col=ACENTO))
        caja.add_widget(t)
        self._tarjeta_capital_minimo(d, caja)

        lab = d.get("laboratorio") or {}
        est = lab.get("estado") or {}
        t = Tarjeta(); t.add_widget(Texto("Laboratorio de estrategias", 17, negrita=True))
        t.add_widget(Texto("Busca estrategias nuevas una vez por semana. La que aprueba el examen final queda 3 meses en "
                           "observación sin dinero; si les gana a Breakout y Resorte, entra sola al piloto.", 13, GRIS))
        self._fila_switch(t, "Activo", (lab.get("ajustes") or {}).get("activo"),
                          lambda v: self._accion("laboratorio", activo=v))
        if lab.get("corriendo"):
            t.add_widget(Texto(f"Buscando ahora: {est.get('mensaje', '')}", 13))
        elif est.get("fin"):
            t.add_widget(Texto(f"Última búsqueda: {datetime.fromtimestamp(est['fin']):%d/%m %H:%M}. Probó "
                               f"{est.get('probadas', 0)} combinaciones.", 13))
        else:
            t.add_widget(Texto("Todavía no buscó.", 13, GRIS))
        t.add_widget(Boton("Buscar ahora", lambda: self._accion("buscar_estrategias",
                                                                 "Búsqueda iniciada: tarda unos 30 minutos.")))
        for c in lab.get("candidatas") or []:
            ob = c.get("observacion") or {}
            txt = (f"{c.get('nombre', c['id'])}: en observación · ella {pct(ob.get('ella'), 1, True)}, Breakout y Resorte "
                   f"{pct(ob.get('base'), 1, True)}" if ob.get("ella") is not None else
                   f"{c.get('nombre', c['id'])}: en observación (todavía sin resultado)")
            t.add_widget(Texto(txt, 13))
            t.add_widget(Boton("Dejar de observarla", lambda i=c["id"]: preguntar(
                "Laboratorio", "¿Dejar de observar esta estrategia?", "Sí",
                lambda: self._accion("descartar_candidata", id=i))))
        caja.add_widget(t)

        a = d.get("actualizacion") or {}
        t = Tarjeta(); t.add_widget(Texto("Actualizaciones del servidor", 17, negrita=True))
        t.add_widget(Texto("El servidor busca versiones nuevas cada hora.", 13, GRIS))
        t.add_widget(Texto({"al día": f"Al día (versión {d.get('version')}).",
                            "disponible": f"Hay una versión nueva: {a.get('version')}.",
                            "instalada": f"Versión {a.get('version')} instalada; el servidor se está reiniciando.",
                            "error": f"No se pudo buscar: {a.get('detalle', '')}"}.get(a.get("estado"),
                                                                                      "Todavía no buscó."), 13))
        self._fila_switch(t, "Instalar solas", d.get("actualizaciones_auto", True),
                          lambda v: self._accion("actualizaciones_auto", activo=v))
        t.add_widget(Boton("Buscar ahora", lambda: self._accion("buscar_actualizacion")))
        t.add_widget(Boton("Instalar", lambda: self._accion(
            "instalar_actualizacion", "Si había una versión nueva, se instaló y el servidor se reinicia (tarda menos de "
                                      "un minuto)."), col=ACENTO))
        caja.add_widget(t)
        self.cuerpo.add_widget(sv)

if __name__ == "__main__":
    ControlApp().run()
