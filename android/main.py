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

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.properties import BooleanProperty
from kivy.uix.widget import Widget
from kivy.uix.textinput import TextInput
from kivy.utils import get_color_from_hex as hexc, platform

import cliente_api as C

# ---------- temas (oscuro: azul noche; claro: gris azulado). Los colores son globales: al cambiar el tema se rearma todo.
TEMAS = {
    "oscuro": dict(FONDO="#0a0f1c", BARRA="#0a0f1c", PANEL="#141b2d", CUADRO="#1b2440", BORDE="#22304d",
                   TEXTO="#eef2fb", GRIS="#8e9ab5", VERDE="#34d399", ROJO="#fb7185", AMBAR="#f5b83d", ACENTO="#ff8a1f",
                   SOBRE_ACENTO="#111111", SOMBRA="#00000066", VELO="#0000008c", SUAVE="#ff8a1f29"),
    "claro": dict(FONDO="#eef2f8", BARRA="#ffffff", PANEL="#ffffff", CUADRO="#f2f5fb", BORDE="#d9e1ee",
                  TEXTO="#111a2e", GRIS="#5d6982", VERDE="#0f9f6e", ROJO="#e11d48", AMBAR="#b7791f", ACENTO="#ea6c00",
                  SOBRE_ACENTO="#ffffff", SOMBRA="#1e325a1a", VELO="#0f19325a", SUAVE="#ffe9d5ff"),
}
FONDO = BARRA = PANEL = CUADRO = BORDE = TEXTO = GRIS = VERDE = ROJO = AMBAR = ACENTO = SOBRE_ACENTO = None
SOMBRA = VELO = SUAVE = None
TEMA = "oscuro"


def aplicar_tema(nombre):
    global TEMA
    TEMA = nombre if nombre in TEMAS else "oscuro"
    globals().update({k: hexc(v) for k, v in TEMAS[TEMA].items()})
    Window.clearcolor = FONDO


aplicar_tema("oscuro")
Window.softinput_mode = "below_target"  # que el teclado no tape el campo donde se escribe
PIL_BASE = ("BREAKOUT", "TL")

# íconos: fuente Material Icons de Google (licencia Apache 2.0), en iconos.ttf
_AQUI = os.path.dirname(os.path.abspath(__file__))
for _f in (os.path.join(_AQUI, "iconos.ttf"), os.path.join(os.path.dirname(_AQUI), "iconos.ttf")):
    if os.path.exists(_f):
        LabelBase.register("Iconos", _f)
        HAY_ICONOS = True
        break
else:
    HAY_ICONOS = False
ICONOS = {"resumen": "\ue88a", "posiciones": "\ue53b", "operaciones": "\ue241", "estrategias": "\uea4b",
          "decisiones": "\uf184", "avisos": "\ue7f4", "control": "\ue429", "servidor": "\ue8b8", "menu": "\ue5d2"}
PESTANAS = (("resumen", "Resumen"), ("posiciones", "Posiciones"), ("operaciones", "Operaciones"),
            ("estrategias", "Estrategias"), ("decisiones", "Decisiones"), ("avisos", "Avisos"), ("control", "Control"),
            ("servidor", "Configuración"))


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


def alfa(col, a):
    return [col[0], col[1], col[2], a]


def fondo(w, col, radio=10, borde=None, franja=None, sombra=False):
    """Dibuja detrás del widget un rectángulo redondeado; con borde (color), una franja de color a la izquierda y sombra."""
    def dibujar(*_):
        w.canvas.before.clear()
        with w.canvas.before:
            x, y, an, al, r = w.x, w.y, w.width, w.height, dp(radio)
            if sombra and SOMBRA[3] > 0:
                Color(*SOMBRA); RoundedRectangle(pos=(x, y - dp(3)), size=(an, al), radius=[r])
            dentro = 0
            if franja is not None:
                Color(*franja); RoundedRectangle(pos=(x, y), size=(an, al), radius=[r]); dentro = dp(3)
            elif borde is not None:
                Color(*borde); RoundedRectangle(pos=(x, y), size=(an, al), radius=[r]); dentro = dp(1)
            Color(*col)
            if franja is not None:
                RoundedRectangle(pos=(x + dentro, y + dp(1)), size=(an - dentro - dp(1), al - dp(2)),
                                 radius=[dp(3), r, r, dp(3)])
            else:
                RoundedRectangle(pos=(x + dentro, y + dentro), size=(an - 2 * dentro, al - 2 * dentro),
                                 radius=[max(0, r - dentro)])
    w.bind(pos=dibujar, size=dibujar)
    dibujar()


class Texto(Label):
    def __init__(self, texto="", tam=15, col=None, negrita=False, **kw):
        kw.setdefault("pos_hint", {"center_y": 0.5})  # centrado cuando va en una fila; en columnas no influye
        super().__init__(text=texto, font_size=sp(tam), color=col or TEXTO, bold=negrita, halign="left",
                         valign="middle", size_hint_y=None, **kw)
        self.bind(width=lambda *_: setattr(self, "text_size", (self.width, None)))
        self.bind(texture_size=lambda *_: setattr(self, "height", self.texture_size[1] + dp(6)))
        self.height = dp(6) if not texto else self.height  # sin texto no hay textura: que no quede con el alto por defecto


class Interruptor(ButtonBehavior, Widget):
    """Llave de encendido/apagado con los colores del tema (naranja encendida)."""
    active = BooleanProperty(False)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self._dibujar, size=self._dibujar, active=self._dibujar)
        self._dibujar()

    def on_release(self):
        self.active = not self.active

    def _dibujar(self, *_):
        self.canvas.clear()
        an, al = dp(52), dp(30)
        x, y = self.right - an - dp(4), self.center_y - al / 2
        with self.canvas:
            Color(*(ACENTO if self.active else BORDE)); RoundedRectangle(pos=(x, y), size=(an, al), radius=[al / 2])
            Color(*(SOBRE_ACENTO if self.active and TEMA == "claro" else (1, 1, 1, 1)))
            d = al - dp(6)
            RoundedRectangle(pos=(x + an - d - dp(3) if self.active else x + dp(3), y + dp(3)), size=(d, d), radius=[d / 2])


class Ruedita(Widget):
    """Ruedita de "cargando" (un arco que gira). mostrar(True/False)."""
    def __init__(self, **kw):
        kw.setdefault("size_hint", (None, None)); kw.setdefault("size", (dp(26), dp(26)))
        super().__init__(**kw)
        self.angulo, self._reloj = 0, None
        self.opacity = 0
        self.bind(pos=self._dibujar, size=self._dibujar)

    def mostrar(self, si):
        if si and self._reloj is None:
            self.opacity = 1
            self._reloj = Clock.schedule_interval(self._girar, 1 / 30)
        elif not si and self._reloj is not None:
            self._reloj.cancel(); self._reloj = None
            self.opacity = 0

    def _girar(self, dt):
        self.angulo = (self.angulo + 360 * dt * 1.2) % 360
        self._dibujar()

    def _dibujar(self, *_):
        self.canvas.clear()
        r = min(self.width, self.height) / 2 - dp(3)
        with self.canvas:
            Color(*alfa(ACENTO, 0.25)); Line(circle=(self.center_x, self.center_y, r), width=dp(1.6))
            Color(*ACENTO); Line(circle=(self.center_x, self.center_y, r, self.angulo, self.angulo + 100), width=dp(1.6))


class Refrescable(ScrollView):
    """Pantalla deslizable con "tirar para actualizar": arrastrando hacia abajo estando arriba de todo."""
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            arriba = self.scroll_y >= 0.999 or not self.children or self.children[0].height <= self.height
            touch.ud.setdefault("tirar", (touch.y, arriba))
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        info = touch.ud.get("tirar")
        if info and info[1] and not touch.ud.get("tirado") and info[0] - touch.y > dp(80):
            touch.ud["tirado"] = True  # una sola vez por gesto, apenas pasa el umbral
            app = App.get_running_app()
            if app is not None and hasattr(app, "_refrescar"):
                app._refrescar()
        return super().on_touch_move(touch)


class Rotulo(Label):
    """Etiqueta de una línea alineada dentro de su espacio (halign/valign)."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(size=lambda *_: setattr(self, "text_size", self.size))


class Icono(Label):
    def __init__(self, clave, tam=22, col=None, **kw):
        super().__init__(text=ICONOS.get(clave, "") if HAY_ICONOS else "", font_name="Iconos" if HAY_ICONOS else "Roboto",
                         font_size=sp(tam), color=col or TEXTO, size_hint=(None, None), size=(dp(tam + 10), dp(tam + 10)),
                         **kw)


class Boton(ButtonBehavior, Label):
    """Botón redondeado. col=ACENTO: principal (relleno naranja); col=ROJO: peligro (borde rojo); si no, secundario."""
    def __init__(self, texto, accion, col=None, **kw):
        tipo = "primario" if col == ACENTO else "peligro" if col == ROJO else "normal"
        letra = SOBRE_ACENTO if tipo == "primario" else ROJO if tipo == "peligro" else TEXTO
        super().__init__(text=texto, font_size=sp(15), size_hint_y=None, height=dp(46), color=letra,
                         bold=tipo == "primario", halign="center", valign="middle", **kw)
        self.bind(size=lambda *_: setattr(self, "text_size", (self.width - dp(16), None)))
        relleno = ACENTO if tipo == "primario" else alfa(ROJO, 0.08) if tipo == "peligro" else CUADRO
        borde = None if tipo == "primario" else alfa(ROJO, 0.55) if tipo == "peligro" else BORDE
        fondo(self, relleno, 10, borde=borde)
        self.bind(state=lambda *_: setattr(self, "opacity", 0.7 if self.state == "down" else 1))
        self.bind(on_release=lambda *_: accion())


class Tarjeta(BoxLayout):
    def __init__(self, franja=None, **kw):
        kw.setdefault("padding", dp(14))
        kw.setdefault("spacing", dp(6))
        super().__init__(orientation="vertical", size_hint_y=None, **kw)
        self.bind(minimum_height=self.setter("height"))
        fondo(self, PANEL, 14, borde=BORDE, franja=franja, sombra=True)


class Pildora(Label):
    """Etiqueta redondeada con el estado (Corriendo, Detenido...)."""
    def __init__(self, texto="", col=None, **kw):
        super().__init__(text=texto, font_size=sp(13), bold=True, size_hint=(None, None), height=dp(28), **kw)
        self.bind(texture_size=lambda *_: setattr(self, "width", self.texture_size[0] + dp(24)))
        self.poner(texto, col or VERDE)

    def poner(self, texto, col):
        self.text, self.color = texto, col
        fondo(self, alfa(col, 0.15), 14)


def seccion(caja, texto, derecha=""):
    """Título de sección arriba de la tarjeta (gris, en mayúsculas), con un dato opcional a la derecha."""
    f = BoxLayout(size_hint_y=None, height=dp(30), padding=(dp(4), dp(10), dp(4), 0))
    f.add_widget(Rotulo(text=texto.upper(), font_size=sp(12), bold=True, color=GRIS, halign="left", valign="bottom",
                       size_hint_x=1, shorten=True))
    if derecha:
        f.add_widget(Rotulo(text=derecha, font_size=sp(12), color=GRIS, halign="right", valign="bottom", size_hint_x=0.5))
    caja.add_widget(f)


def cuadro(titulo, valor, col=None):
    """Cuadrito con un dato: título chico y valor en negrita."""
    c = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(62), padding=(dp(12), dp(8)), spacing=dp(2))
    fondo(c, CUADRO, 10)
    c.add_widget(Texto(titulo, 12, GRIS))
    c.add_widget(Texto(valor, 15, col, negrita=True))
    return c


def cuadros(items, cols=2):
    g = GridLayout(cols=cols, size_hint_y=None, spacing=dp(8))
    g.bind(minimum_height=g.setter("height"))
    for it in items:
        g.add_widget(cuadro(*it))
    return g


def separador():
    s = BoxLayout(size_hint_y=None, height=dp(1))
    fondo(s, BORDE, 0)
    return s


class Entrada(TextInput):
    def __init__(self, **kw):
        kw.pop("background_color", None); kw.pop("foreground_color", None)
        super().__init__(background_normal="", background_active="", background_color=CUADRO, foreground_color=TEXTO,
                         cursor_color=ACENTO, hint_text_color=GRIS, padding=(dp(12), dp(11)), **kw)


def pagina():
    sv = Refrescable(do_scroll_x=False, bar_width=dp(3), bar_color=alfa(GRIS, 0.5), bar_inactive_color=alfa(GRIS, 0.2))
    caja = BoxLayout(orientation="vertical", size_hint_y=None, padding=(dp(14), dp(6), dp(14), dp(18)), spacing=dp(10))
    caja.bind(minimum_height=caja.setter("height"))
    sv.add_widget(caja)
    return sv, caja


def _popup(titulo, caja, alto, cerrar_solo=True):
    return Popup(title=titulo, content=caja, size_hint=(0.92, None), height=dp(alto), auto_dismiss=cerrar_solo,
                 background="", background_color=PANEL, title_color=TEXTO, title_size=sp(17), separator_color=ACENTO,
                 overlay_color=VELO)


def preguntar(titulo, texto, si, accion, al_cancelar=None):
    caja = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(12))
    caja.add_widget(Texto(texto))
    fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
    pop = _popup(titulo, caja, 300, False)
    fila.add_widget(Boton("Cancelar", lambda: (pop.dismiss(), al_cancelar and al_cancelar())))
    fila.add_widget(Boton(si, lambda: (pop.dismiss(), accion()), col=ACENTO))
    caja.add_widget(fila)
    pop.open()


def avisar(titulo, texto):
    caja = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(12))
    caja.add_widget(Texto(texto))
    pop = _popup(titulo, caja, 280)
    caja.add_widget(Boton("OK", pop.dismiss, col=ACENTO))
    pop.open()


class ItemMenu(ButtonBehavior, BoxLayout):
    def __init__(self, clave, texto, activo, accion, extra="", **kw):
        super().__init__(size_hint_y=None, height=dp(50), padding=(dp(14), 0), spacing=dp(14), **kw)
        col = ACENTO if activo else TEXTO
        if activo:
            fondo(self, SUAVE, 10)
        self.add_widget(Icono(clave, 22, col, pos_hint={"center_y": 0.5}))
        self.add_widget(Rotulo(text=texto, font_size=sp(15.5), bold=activo, color=col, halign="left", valign="middle"))
        if extra:
            self.add_widget(Pildora(extra, ACENTO, pos_hint={"center_y": 0.5}))
        self.bind(state=lambda *_: setattr(self, "opacity", 0.7 if self.state == "down" else 1))
        self.bind(on_release=lambda *_: accion())


class ControlApp(App):
    title = "Bot de trading"

    def on_pause(self):
        self.en_frente = False  # con la app cerrada o en segundo plano, los avisos llegan por push (Firebase)
        return True  # al salir de la app, Android la deja en pausa en lugar de cerrarla

    def on_resume(self):
        self._primer_vistazo = True  # lo que pasó mientras estaba cerrada ya llegó por push: no repetirlo
        self.en_frente = True
        if getattr(self, "cliente", None):
            self._refrescar()  # los datos en pantalla son de cuando se cerró: traer los de ahora (con ruedita)
            if getattr(self, "datos", None):
                Clock.schedule_once(lambda dt: self._pintar(), 0.3)

    def build(self):
        self.archivo = os.path.join(self.user_data_dir, "codigo.json")
        self.cliente, self.datos, self.error, self.pestana = None, None, None, "resumen"
        self.en_frente, self._primer_vistazo = True, True
        self.despertar = threading.Event()  # despierta al sondeo para pedir los datos ya
        aplicar_tema((self._leer_json("tema.json") or {}).get("tema", "oscuro"))
        self.base = FloatLayout()  # abajo la pantalla; arriba, cuando se abre, el menú
        self.raiz = BoxLayout(orientation="vertical")
        self.base.add_widget(self.raiz)
        self.menu = None
        Window.bind(on_keyboard=self._tecla)
        if platform == "android":
            try:
                import instalador
                instalador.escuchar(self._error_instalacion)
            except Exception:
                pass
        cod = self._leer_codigo()
        if cod:
            self._conectar(cod)
        else:
            self._pantalla_codigo()
        return self.base

    def _tecla(self, _w, tecla, *_):
        if tecla == 27 and self.menu is not None:  # botón "atrás" de Android con el menú abierto: lo cierra
            self._cerrar_menu()
            return True
        return False

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
        caja.add_widget(Texto("Si ya tenés un servidor, pegá su código de conexión (empieza con BOT1-). Lo muestra la app "
                              "de Windows (Configuración) o el servidor con: venv/bin/python servidor.py codigo", 14, GRIS))
        if error:
            caja.add_widget(Texto(error, 14, ROJO))
        entrada = Entrada(multiline=True, size_hint_y=None, height=dp(140), font_size=sp(14),
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
        pend = self._leer_json("servidor_pendiente.json") or {}
        t = Tarjeta()
        t.add_widget(Texto("¿Todavía no tenés servidor?", 17, negrita=True))
        t.add_widget(Texto("La app lo crea gratis en Oracle Cloud y deja el bot funcionando. Solo necesitás una cuenta de "
                           "Oracle (y después una de Binance).", 13, GRIS))
        if pend.get("ip"):
            t.add_widget(Boton(f"Terminar de conectar el servidor que se estaba creando ({pend['ip']})",
                               self._reanudar_servidor, col=ACENTO))
        t.add_widget(Boton("Crear mi servidor en Oracle", self._asistente_inicio, col=ACENTO if not pend.get("ip") else None))
        caja.add_widget(t)
        self.raiz.add_widget(sv)

    def _conectar(self, cod):
        try:
            self.cliente = C.Cliente(cod)
        except ValueError as e:
            return self._pantalla_codigo(str(e))
        self._mostrar_carga = True  # ruedita hasta que lleguen los primeros datos
        self._armar()
        if not getattr(self, "_sondeando", False):
            self._sondeando = True
            threading.Thread(target=self._sondeo, daemon=True).start()
        if self._avisos_activos():
            self._activar_push()

    # ---------- asistente: crear el servidor en Oracle Cloud desde el celular (oci_api.py + claves de Java)
    def _arch(self, nombre):
        return os.path.join(self.user_data_dir, nombre)

    def _leer_json(self, nombre):
        try:
            with open(self._arch(nombre), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _escribir_json(self, nombre, datos):
        with open(self._arch(nombre), "w", encoding="utf-8") as f:
            json.dump(datos, f)

    def _clave_oracle(self):
        """Clave de API de Oracle de este celular (se genera una vez y queda en el almacenamiento privado de la app)."""
        import base64
        import cripto_android as K
        g = self._leer_json("oracle_clave_api.json") or {}
        if g.get("priv"):
            priv = base64.b64decode(g["priv"])
            pub, huella = K.publica_de(priv)
        else:
            priv, pub, huella = K.generar_clave_api()
            self._escribir_json("oracle_clave_api.json", {"priv": base64.b64encode(priv).decode()})
        return priv, pub, huella

    def _pantalla(self, titulo, texto=""):
        self.raiz.clear_widgets()
        sv, caja = pagina()
        caja.add_widget(Texto(titulo, 22, negrita=True))
        if texto:
            caja.add_widget(Texto(texto, 14, GRIS))
        self.raiz.add_widget(sv)
        return caja

    def _abrir_url(self, url):
        if platform != "android":
            import webbrowser
            return webbrowser.open(url)
        from jnius import autoclass
        Intent, Uri = autoclass("android.content.Intent"), autoclass("android.net.Uri")
        autoclass("org.kivy.android.PythonActivity").mActivity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))

    def _copiar(self, texto, boton):
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(texto)
            antes, boton.text = boton.text, "Copiado"
            Clock.schedule_once(lambda dt: setattr(boton, "text", antes), 2)
        except Exception as e:
            avisar("Copiar", f"No se pudo copiar: {e}")

    def _texto_fijo(self, texto, alto=130):
        return Entrada(text=texto, readonly=True, multiline=True, size_hint_y=None, height=dp(alto), font_size=sp(11),
                         background_color=PANEL, foreground_color=TEXTO)

    def _volver_inicio(self):
        if self.cliente:
            self.pestana = "servidor"; self._armar()
        else:
            self._pantalla_codigo()

    def _pantalla_encendida(self, si):
        """Mientras se crea el servidor, que el celular no apague la pantalla (Android frena las apps en segundo plano)."""
        if platform != "android":
            return
        try:
            from android.runnable import run_on_ui_thread
            from jnius import autoclass

            @run_on_ui_thread
            def poner():
                w = autoclass("org.kivy.android.PythonActivity").mActivity.getWindow()
                fl = autoclass("android.view.WindowManager$LayoutParams").FLAG_KEEP_SCREEN_ON
                w.addFlags(fl) if si else w.clearFlags(fl)
            poner()
        except Exception:
            pass

    def _asistente_inicio(self):
        caja = self._pantalla("Tu servidor gratis en Oracle Cloud", (
            "El bot corre en una máquina gratis de Oracle, así funciona las 24 horas aunque cierres la app. La app la "
            "crea y la deja funcionando sola; vos solo necesitás una cuenta de Oracle Cloud."))
        caja.add_widget(Texto(
            "1. Si no tenés cuenta, creala en oracle.com/cloud/free (\"Start for free\"). Oracle pide una tarjeta solo "
            "para verificar tu identidad: con los recursos Always Free no cobra nada.\n\n"
            "2. MUY IMPORTANTE: como región de inicio (Home Region) elegí Brazil East (Sao Paulo) o Chile Central "
            "(Santiago). Binance bloquea los servidores de Estados Unidos y la región no se puede cambiar después.\n\n"
            "3. Esperá el mail de que la cuenta está lista y entrá a cloud.oracle.com.", 14))
        caja.add_widget(Boton("Crear cuenta de Oracle", lambda: self._abrir_url("https://www.oracle.com/cloud/free/")))
        caja.add_widget(Boton("Ya tengo la cuenta: seguir", self._asistente_clave, col=ACENTO))
        caja.add_widget(Boton("Volver", self._volver_inicio))

    def _asistente_clave(self, error=""):
        try:
            priv, pub, huella = self._clave_oracle()
        except Exception as e:
            return avisar("Clave de API", f"No se pudo generar la clave: {type(e).__name__}: {e}")
        caja = self._pantalla("Darle permiso a la app", (
            "La app necesita una clave de API de Oracle para crear la máquina. La generó recién: agregá esta clave "
            "pública en tu perfil de Oracle y pegá acá el texto que Oracle te muestra."))
        caja.add_widget(Texto(
            "1. En cloud.oracle.com tocá el ícono de tu perfil (arriba a la derecha) › \"My profile\" (Mi perfil) › "
            "sección \"API keys\" › \"Add API key\".\n"
            "2. Elegí \"Paste a public key\" (Pegar una clave pública), pegá la clave de abajo y tocá \"Add\".", 14))
        bc = Boton("Copiar", lambda: None)
        bc.bind(on_release=lambda *_: self._copiar(pub, bc))
        caja.add_widget(self._texto_fijo(pub, 150)); caja.add_widget(bc)
        caja.add_widget(Texto("3. Oracle muestra \"Configuration file preview\": copiá todo ese texto (empieza con "
                              "[DEFAULT]) y pegalo acá.", 14))
        if error:
            caja.add_widget(Texto(error, 14, ROJO))
        entrada = Entrada(multiline=True, size_hint_y=None, height=dp(150), font_size=sp(12), background_color=PANEL,
                            foreground_color=TEXTO, hint_text="[DEFAULT]\nuser=ocid1.user.oc1..\nfingerprint=…\n"
                                                              "tenancy=ocid1.tenancy.oc1..\nregion=sa-saopaulo-1")
        caja.add_widget(entrada)

        def pegar():
            try:
                from kivy.core.clipboard import Clipboard
                entrada.text = (Clipboard.paste() or "").strip()
            except Exception:
                pass
        caja.add_widget(Boton("Pegar el texto copiado", pegar))

        def crear():
            import oci_api as O
            try:
                cfg = O.leer_configuracion(entrada.text)
            except ValueError as e:
                return self._asistente_clave(str(e))
            if cfg["fingerprint"].lower() != huella:
                return self._asistente_clave(
                    "La huella (fingerprint) del texto pegado no coincide con la clave de esta app. Revisá que hayas "
                    "agregado la clave pública que muestra esta pantalla.")
            if cfg["region"] not in O.REGIONES_OK:
                return self._asistente_clave(
                    f"Tu cuenta de Oracle está en la región {cfg['region']}. Hace falta una cuenta con región de inicio "
                    "Sao Paulo o Santiago: Binance no funciona desde los servidores de Estados Unidos.")
            self._asistente_progreso()
            threading.Thread(target=self._asistente_trabajo, args=(cfg, priv), daemon=True).start()
        caja.add_widget(Boton("Crear el servidor", crear, col=ACENTO))
        caja.add_widget(Boton("Volver", self._asistente_inicio))

    def _asistente_progreso(self, ip=None):
        self._cancelar_asistente = False
        caja = self._pantalla("Creando tu servidor", (
            "Tarda unos 15 minutos: Oracle crea la máquina y después el bot se instala solo. Dejá la app abierta (la "
            "pantalla queda encendida); si se cierra, al volver a abrirla podés seguir esperando."))
        self.log_asistente = Texto("", 13)
        caja.add_widget(self.log_asistente)
        self.caja_asistente = caja
        self.btn_asistente = Boton("Cancelar", self._cancelar_creacion)
        caja.add_widget(self.btn_asistente)
        self._pantalla_encendida(True)

    def _cancelar_creacion(self):
        self._cancelar_asistente = True
        self._pantalla_encendida(False)
        self._volver_inicio()

    @mainthread
    def _log(self, texto):
        if getattr(self, "log_asistente", None) is not None:
            self.log_asistente.text += f"{time.strftime('%H:%M')}  {texto}\n"

    def _asistente_trabajo(self, cfg, priv):
        import cripto_android as K
        import oci_api as O
        try:
            token = O.nuevo_token()
            ssh_priv, ssh_pub = K.generar_ssh()
            self._escribir_json("servidor_pendiente.json", {"token": token})
            res = O.crear_servidor(O.OCI(cfg, firmar=K.firmador(priv)), O.script_arranque(token), ssh_pub,
                                   log=self._log, cancelado=lambda: self._cancelar_asistente)
            self._escribir_json("servidor_pendiente.json", {"token": token, "ip": res["ip"], "forma": res["forma"]})
            with open(self._arch(f"ssh-{res['ip']}.key"), "w", encoding="utf-8") as f:
                f.write(ssh_priv)
            self._esperar_servidor(res["ip"], token, res["forma"])
        except Exception as e:
            self._asistente_error(f"{type(e).__name__}: {e}")
        finally:
            K.soltar_hilo()

    def _esperar_servidor(self, ip, token, forma=""):
        """El bot se instala solo en la máquina; cuando responde, la app aprende la huella de su certificado (lo creó el
        servidor) y arma el código de conexión."""
        import oci_api as O
        self._log(f"Máquina lista en {ip}. Instalando el bot (unos 10 minutos)…")
        fin = time.time() + 30 * 60
        while not self._cancelar_asistente:
            try:
                codigo = O.codigo_conexion(ip, token, O.huella_servidor(ip))
                C.Cliente(codigo).estado()
                break
            except (OSError, C.ErrorConexion, C.ErrorServidor):
                if time.time() > fin:
                    return self._asistente_error("El servidor no respondió en 30 minutos. Puede que la instalación "
                                                 "siga: volvé a abrir la app más tarde y tocá \"Terminar de conectar\".")
                time.sleep(20)
        else:
            return
        self._guardar_codigo(codigo)
        try:
            os.remove(self._arch("servidor_pendiente.json"))
        except OSError:
            pass
        self._asistente_listo(codigo, ip, forma)

    def _reanudar_servidor(self):
        p = self._leer_json("servidor_pendiente.json") or {}
        self._asistente_progreso()

        def tarea():
            try:
                self._esperar_servidor(p["ip"], p["token"], p.get("forma", ""))
            except Exception as e:
                self._asistente_error(f"{type(e).__name__}: {e}")
        threading.Thread(target=tarea, daemon=True).start()

    @mainthread
    def _asistente_error(self, texto):
        self._pantalla_encendida(False)
        if getattr(self, "caja_asistente", None) is None:
            return avisar("Servidor", texto)
        self._log("No se pudo terminar: " + texto)
        if self.btn_asistente.parent:
            self.caja_asistente.remove_widget(self.btn_asistente)
        self.caja_asistente.add_widget(Boton("Volver a intentar", self._asistente_clave, col=ACENTO))
        self.caja_asistente.add_widget(Boton("Volver", self._volver_inicio))

    @mainthread
    def _asistente_listo(self, codigo, ip, forma):
        self._pantalla_encendida(False)
        self.caja_asistente = None
        caja = self._pantalla("¡Servidor listo!")
        caja.add_widget(Texto(
            f"El bot ya está corriendo en tu servidor de Oracle ({ip}{', máquina ' + forma if forma else ''}), en modo "
            "simulado: usa precios reales pero todavía no opera. La app quedó conectada.\n\nFalta conectar tu cuenta "
            "de Binance: es el paso siguiente.", 14))

        def seguir():
            self._conectar(codigo)
            self._pantalla_claves("demo")
        caja.add_widget(Boton("Seguir: conectar Binance", seguir, col=ACENTO))

    # ---------- conectar Binance (demo o real): el servidor genera la clave y nunca la entrega
    def _pantalla_claves(self, modo):
        caja = self._pantalla(f"Conectar Binance {'demo' if modo == 'demo' else '(dinero real)'}",
                              "Pidiéndole la clave al servidor…")

        def tarea():
            try:
                r = self.cliente.accion("claves_iniciar", modo=modo)
                self._pantalla_claves2(modo, r["publica"], r.get("ip") or "?")
            except (C.ErrorConexion, C.ErrorServidor, KeyError) as e:
                self._avisar("Binance", str(e))
        threading.Thread(target=tarea, daemon=True).start()
        caja.add_widget(Boton("Volver", self._volver_inicio))

    @mainthread
    def _pantalla_claves2(self, modo, pub, ip):
        url = {"demo": "https://demo.binance.com/es/my/settings/api-management",
               "real": "https://www.binance.com/es/my/settings/api-management"}[modo]
        caja = self._pantalla("Conectar tu cuenta de Binance", (
            "Tu servidor generó una clave para Binance. La parte privada nunca sale del servidor: a Binance solo le das "
            "la parte pública, y a la app solo la API key que te devuelve Binance."))
        caja.add_widget(Texto(f"1. Abrí la gestión de API de Binance{' demo' if modo == 'demo' else ''} › \"Crear API\" "
                              "› \"Autogenerada\".\n2. Pegá esta clave pública completa (con las líneas BEGIN y END):",
                              14))
        caja.add_widget(Boton("Abrir Binance", lambda: self._abrir_url(url)))
        bc = Boton("Copiar", lambda: None)
        bc.bind(on_release=lambda *_: self._copiar(pub, bc))
        caja.add_widget(self._texto_fijo(pub, 110)); caja.add_widget(bc)
        if modo == "demo":
            pasos = ("3. Ponele un nombre y confirmá. En la demo los permisos ya vienen listos (no se pueden cambiar) y "
                     "la restricción de IP no hace falta.\n4. Copiá la API Key que te muestra Binance y pegala acá:")
        else:
            pasos = ("3. Ponele un nombre y confirmá.\n4. En la clave nueva tocá \"Editar restricciones\": activá solo "
                     "\"Habilitar futuros\" (sin retiros) y en \"Restringir el acceso a IP de confianza\" agregá la IP de "
                     f"tu servidor: {ip}. Guardá. Sin esto el bot no deja operar con dinero real.\n"
                     "5. Copiá la API Key que te muestra Binance y pegala acá:")
        caja.add_widget(Texto(pasos, 14))
        entrada = Entrada(multiline=False, size_hint_y=None, height=dp(44), font_size=sp(13), hint_text="API Key",
                            background_color=PANEL, foreground_color=TEXTO)
        caja.add_widget(entrada)

        def pegar():
            try:
                from kivy.core.clipboard import Clipboard
                entrada.text = "".join((Clipboard.paste() or "").split())
            except Exception:
                pass
        caja.add_widget(Boton("Pegar la API Key copiada", pegar))
        res = Texto("", 14)
        caja.add_widget(res)

        def probar():
            key = "".join(entrada.text.split())
            if not key:
                return
            res.text, res.color = "Probando la conexión con Binance…", GRIS

            def tarea():
                try:
                    r = self.cliente.accion("claves_completar", modo=modo, api_key=key)
                    self._claves_ok(modo, r, res)
                except (C.ErrorConexion, C.ErrorServidor) as e:
                    self._texto_en(res, f"No funcionó: {e}", ROJO)
            threading.Thread(target=tarea, daemon=True).start()
        caja.add_widget(Boton("Probar y guardar", probar, col=ACENTO))
        caja.add_widget(Boton("Cancelar", self._volver_inicio))

    @mainthread
    def _texto_en(self, label, texto, col=TEXTO):
        label.text, label.color = texto, col

    @mainthread
    def _claves_ok(self, modo, r, res):
        s = r.get("saldo") or {}
        txt = f"Conexión OK. Saldo en futuros: {num(s.get('total', 0))} USDT."
        p = r.get("permisos")
        if p and (p.get("retiros") or not p.get("ip") or not p.get("futuros")):
            res.text, res.color = (txt + "\n\nPara dinero real la clave tiene que tener futuros habilitados, retiros "
                                   "deshabilitados y restricción de IP. Corregilo en Binance y volvé a probar."), AMBAR
            return
        res.text, res.color = txt, VERDE
        if modo == "demo":
            preguntar("Binance conectado", txt + "\n\n¿Pasar el bot a modo demo ahora? Va a operar la cuenta demo de "
                                                 "Binance.", "Sí, cambiar", lambda: self._cambiar_modo("demo"),
                      self._volver_inicio)
        else:
            self._confirmar_real(txt)

    def _confirmar_real(self, txt):
        caja = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        caja.add_widget(Texto(txt + "\n\nVas a operar con DINERO REAL y podés perder dinero. Revisá el capital del modo "
                                    "real en Configuración.\n\nEscribí REAL para pasar a dinero real ahora:", 14))
        e = Entrada(multiline=False, size_hint_y=None, height=dp(44), font_size=sp(15))
        caja.add_widget(e)
        fila = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        pop = Popup(title="Dinero real", content=caja, size_hint=(0.94, None), height=dp(420), auto_dismiss=False)

        def ok():
            pop.dismiss()
            if e.text.strip() == "REAL":
                self._cambiar_modo("real", "REAL")
            else:
                self._volver_inicio()
        fila.add_widget(Boton("Después", lambda: (pop.dismiss(), self._volver_inicio())))
        fila.add_widget(Boton("Confirmar", ok, col=ROJO))
        caja.add_widget(fila)
        pop.open()

    def _cambiar_modo(self, modo, confirmar=None):
        datos = {"modo": modo}
        if confirmar:
            datos["confirmar"] = confirmar

        def tarea():
            try:
                self.cliente.accion("cambiar_modo", **datos)
                self._avisar("Modo cambiado", "Listo. El servidor se reinicia para aplicar el cambio (menos de un "
                                              "minuto).")
            except (C.ErrorConexion, C.ErrorServidor) as e:
                self._avisar("Modo", str(e))
            self._volver_en_hilo()
        threading.Thread(target=tarea, daemon=True).start()

    @mainthread
    def _volver_en_hilo(self):
        self._volver_inicio()

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
        """Fuera de Android (pruebas en la PC) solo abre el link del APK."""
        import avisos as AV
        import webbrowser
        webbrowser.open(AV.URL_APK)

    def _actualizar(self, auto=False):
        """Baja el APK nuevo e instala la actualización desde la app (instalador.py)."""
        if platform != "android":
            return None if auto else self._bajar_version()
        if getattr(self, "act_estado", None) in ("bajando", "instalando"):
            return
        self.act_estado, self.act_avance = "bajando", 0.0
        self._pintar()

        def tarea():
            import avisos as AV
            import instalador as IN
            try:
                ruta = IN.bajar(AV.URL_APK, os.path.join(self.user_data_dir, "actualizacion.apk"), self._avance_act)
                self.act_estado = "instalando"
                self._pintar()
                IN.instalar(ruta)
            except Exception as e:
                if "404" in str(e):  # el APK todavía no está en GitHub: esperar y reintentar solo
                    self.act_estado, self._act_auto, self.version_github, self._prox_github = None, False, None, 0
                else:
                    self.act_estado = "error: " + f"{type(e).__name__}: {e}"[:160]
                self._pintar()
            finally:
                try:
                    from jnius import detach
                    detach()
                except Exception:
                    pass
        threading.Thread(target=tarea, daemon=True).start()

    def _avance_act(self, x):
        if int(x * 20) != int(getattr(self, "act_avance", 0) * 20):  # repinta cada 5 %
            self.act_avance = x
            self._pintar()
        self.act_avance = x

    @mainthread
    def _error_instalacion(self, texto):
        self.act_estado = "error: " + texto
        self._pintar()

    def _buscar_version_github(self):
        """Pregunta a GitHub cuál es la última versión (al abrir la app y como mucho cada 2 minutos), así el aviso de
        versión nueva aparece enseguida aunque el servidor todavía no se haya actualizado."""
        if platform != "android" or time.time() < getattr(self, "_prox_github", 0):
            return
        self._prox_github = time.time() + 120

        def tarea():
            import avisos as AV
            try:
                import ssl
                import certifi
                ctx = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                ctx = None
            try:
                v = AV.version_apk_github(contexto=ctx)  # solo cuenta si el APK ya se puede bajar
            except Exception:
                return
            if v != getattr(self, "version_github", None):
                self.version_github = v
                self._pintar()
        threading.Thread(target=tarea, daemon=True).start()

    def _version_disponible(self, d):
        """La más nueva entre la del servidor y la publicada en GitHub."""
        import avisos as AV
        vs = [v for v in (d.get("version"), getattr(self, "version_github", None)) if v]
        return max(vs, key=AV.version_tupla) if vs else None

    def _tarjeta_version(self, d, caja):
        import avisos as AV
        if not hasattr(self, "version_app"):
            self.version_app = self._version_app()
        self._buscar_version_github()
        nueva = self._version_disponible(d)
        if not AV.version_nueva(nueva, self.version_app):
            return
        # el servidor se actualiza antes de que el APK termine de compilarse: hasta que esté, solo avisa
        listo = AV.version_nueva(getattr(self, "version_github", None), self.version_app)
        estado = getattr(self, "act_estado", None)
        if not listo and estado not in ("bajando", "instalando"):
            t = Tarjeta(franja=AMBAR)
            t.add_widget(Texto(f"Versión nueva de la app: {nueva} (tenés la {self.version_app}).", 15, AMBAR,
                               negrita=True))
            t.add_widget(Texto("Se está terminando de publicar. En unos minutos la app la baja y la instala sola.", 13,
                               GRIS))
            caja.add_widget(t)
            return
        if estado is None and platform == "android" and not getattr(self, "_act_auto", False):
            self._act_auto = True  # una vez por apertura de la app: se actualiza sola
            Clock.schedule_once(lambda dt: self._actualizar(auto=True), 1)
            estado = "bajando"
        t = Tarjeta(franja=AMBAR)
        t.add_widget(Texto(f"Versión nueva de la app: {nueva} (tenés la {self.version_app}).", 15, AMBAR,
                           negrita=True))
        if estado == "bajando":
            t.add_widget(Texto(f"Bajando la actualización… {getattr(self, 'act_avance', 0) * 100:.0f} %", 13, GRIS))
        elif estado == "instalando":
            t.add_widget(Texto("Instalando. La app se cierra sola para actualizarse: volvé a abrirla en unos segundos. "
                               "La primera vez Android pide confirmar (y quizá permitir que esta app instale "
                               "actualizaciones); después se actualiza sin preguntar.", 13, GRIS))
        else:
            if estado and estado.startswith("error: "):
                t.add_widget(Texto("No se pudo actualizar: " + estado[7:], 13, ROJO))
            t.add_widget(Texto("Tus datos y el código de conexión se conservan.", 13, GRIS))
            t.add_widget(Boton("Actualizar ahora", lambda: self._actualizar(), col=ACENTO))
        caja.add_widget(t)

    def _cambiar_avisos(self, activo):
        self._guardar_avisos(activo)
        if activo:
            self._activar_push()
        else:
            self._desactivar_push()

    # ---------- estructura: barra de arriba (menú, título y estado) + contenido; las pestañas están en el menú
    def _armar(self):
        self._cerrar_menu(animar=False)
        self.raiz.clear_widgets()
        barra = BoxLayout(size_hint_y=None, height=dp(56), padding=(dp(4), 0, dp(12), 0), spacing=dp(6))
        fondo(barra, BARRA, 0)
        bm = type("BotonMenu", (ButtonBehavior, BoxLayout), {})(size_hint=(None, 1), width=dp(52))
        bm.add_widget(Icono("menu", 24, pos_hint={"center_y": 0.5}))
        bm.bind(on_release=lambda *_: self._abrir_menu())
        barra.add_widget(bm)
        self.titulo = Rotulo(text="", font_size=sp(19), bold=True, color=TEXTO, halign="left", valign="middle")
        barra.add_widget(self.titulo)
        self.ruedita = Ruedita(pos_hint={"center_y": 0.5})
        self.ruedita.mostrar(bool(getattr(self, "_mostrar_carga", False)))
        barra.add_widget(self.ruedita)
        self.pildora = Pildora("Conectando", GRIS, pos_hint={"center_y": 0.5})
        barra.add_widget(self.pildora)
        self.raiz.add_widget(barra)
        self.raiz.add_widget(separador())
        self.linea_error = Texto("", 13, ROJO, padding=(dp(14), dp(4)))  # solo aparece sin conexión
        self.cuerpo = BoxLayout()
        self.raiz.add_widget(self.cuerpo)
        self._ir(getattr(self, "pestana", None) or "resumen")

    def _estado_bot(self):
        """(texto, color) del estado para la píldora."""
        d = self.datos
        if self.error:
            return "Sin conexión", ROJO
        if not d:
            return "Conectando", GRIS
        if d["snap"].get("frenado"):
            return "Frenado", ROJO
        return ("Corriendo", VERDE) if d["bot"].get("corriendo") else ("Detenido", AMBAR)

    def _abrir_menu(self):
        if self.menu is not None:
            return
        capa = FloatLayout()
        velo = type("Velo", (ButtonBehavior, Label), {})()
        fondo(velo, VELO, 0)
        velo.bind(on_release=lambda *_: self._cerrar_menu())
        capa.add_widget(velo)
        ancho = min(dp(310), Window.width * 0.8)
        panel = BoxLayout(orientation="vertical", size_hint=(None, 1), width=ancho, x=-ancho, y=0)
        fondo(panel, PANEL, 0)
        cab = BoxLayout(orientation="vertical", size_hint_y=None, padding=(dp(22), dp(24), dp(22), dp(16)), spacing=dp(4))
        cab.bind(minimum_height=cab.setter("height"))
        cab.add_widget(Texto("Bot de trading", 19, negrita=True))
        d = self.datos or {}
        cab.add_widget(Texto(" · ".join(x for x in (d.get("nombre_modo"), f"servidor {d['version']}" if d.get("version")
                                                    else "") if x) or "Control remoto", 13, GRIS))
        txt, col = self._estado_bot()
        prox = (d.get("bot") or {}).get("proxima_revision")
        if prox and txt == "Corriendo":
            txt += f" · próxima {datetime.fromtimestamp(prox):%H:%M}"
        fila = BoxLayout(size_hint_y=None, height=dp(36), padding=(0, dp(6), 0, 0))
        fila.add_widget(Pildora(txt, col)); fila.add_widget(BoxLayout())
        cab.add_widget(fila)
        panel.add_widget(cab)
        panel.add_widget(separador())
        lista = BoxLayout(orientation="vertical", size_hint_y=None, padding=(dp(10), dp(10)), spacing=dp(2))
        lista.bind(minimum_height=lista.setter("height"))
        sl = d.get("sin_leer") or 0
        for k, n in PESTANAS:
            lista.add_widget(ItemMenu(k, n, k == self.pestana, lambda k=k: (self._cerrar_menu(), self._ir(k)),
                                      extra=str(sl) if k == "avisos" and sl else ""))
        sv = ScrollView(do_scroll_x=False); sv.add_widget(lista)
        panel.add_widget(sv)
        capa.add_widget(panel)
        self.menu = (capa, panel, velo)
        self.base.add_widget(capa)
        velo.opacity = 0
        Animation(x=0, d=0.18, t="out_cubic").start(panel)
        Animation(opacity=1, d=0.18).start(velo)

    def _cerrar_menu(self, animar=True):
        if self.menu is None:
            return
        capa, panel, velo = self.menu
        self.menu = None
        if not animar:
            return self.base.remove_widget(capa)
        a = Animation(x=-panel.width, d=0.15, t="in_cubic")
        a.bind(on_complete=lambda *_: self.base.remove_widget(capa))
        a.start(panel)
        Animation(opacity=0, d=0.15).start(velo)

    def _cambiar_tema(self, nombre):
        self._escribir_json("tema.json", {"tema": nombre})
        aplicar_tema(nombre)
        self._armar()

    def _ir(self, k):
        self.pestana = k
        if k == "decisiones":
            self.rev_idx = 0
            threading.Thread(target=self._traer_decisiones, daemon=True).start()
        self._pintar()

    # ---------- datos
    def _traer_decisiones(self):
        try:
            self.decisiones = self.cliente.detalle("decisiones").get("decisiones") or []
        except Exception as e:
            self.error = str(e)
        self._pintar()

    def _refrescar(self):
        """Pide los datos ya (al volver a la app o al tirar la pantalla hacia abajo) y muestra la ruedita."""
        if not getattr(self, "cliente", None):
            return
        self._mostrar_carga = True
        self._ruedita(True)
        self.despertar.set()

    @mainthread
    def _ruedita(self, si):
        if getattr(self, "ruedita", None) is not None:
            self.ruedita.mostrar(si)

    def _sondeo(self):
        while True:
            pedido = getattr(self, "_mostrar_carga", False)
            self.despertar.clear()
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
            if pedido:
                self._mostrar_carga = False
                self._ruedita(False)
            self._pintar(desde_sondeo=not pedido)  # pedido a mano: rehace también Control y Configuración
            self.despertar.wait(10)

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
        self.titulo.text = dict(PESTANAS).get(self.pestana, "")
        self.pildora.poner(*self._estado_bot())
        self.linea_error.text = ("Sin conexión: " + self.error[:160]) if self.error else ""
        if self.error and self.linea_error.parent is None:
            self.raiz.add_widget(self.linea_error, index=1)  # justo arriba del contenido
        elif not self.error and self.linea_error.parent is not None:
            self.raiz.remove_widget(self.linea_error)
        if desde_sondeo and self.pestana in ("control", "servidor") and self.cuerpo.children:
            return  # no rehace estas pantallas mientras escribís (se actualizan al entrar o al hacer una acción)
        viejo = self.cuerpo.children[0] if self.cuerpo.children else None
        misma = isinstance(viejo, ScrollView) and getattr(self, "_pintada", None) == self.pestana
        if desde_sondeo and misma and getattr(viejo, "_touch", None):
            return  # el dedo está deslizando la pantalla: se actualiza en el próximo sondeo
        lugar = viejo.scroll_y if misma else None
        self.cuerpo.clear_widgets()
        if not d:
            sv, caja = pagina(); caja.add_widget(Texto("Esperando datos del servidor…", 15, GRIS))
            self.cuerpo.add_widget(sv); return
        getattr(self, "_p_" + self.pestana)(d)
        self._pintada = self.pestana
        nuevo = self.cuerpo.children[0] if self.cuerpo.children else None
        if lugar is not None and isinstance(nuevo, ScrollView):
            # al refrescar los datos queda donde estabas, no vuelve arriba (scroll_y: 1 = arriba, 0 = abajo)
            self._mantener_lugar(nuevo, lugar)

    @staticmethod
    def _mantener_lugar(sv, lugar):
        """Pone la pantalla nueva en el mismo lugar que la vieja. Los textos se miden en los cuadros siguientes: mientras
        el contenido todavía es más bajo que la pantalla, Kivy fuerza scroll_y a 1 (arriba). Por eso se vuelve a poner
        el lugar cada vez que el contenido crece, durante el primer segundo y salvo que el dedo ya esté moviéndola."""
        caja = sv.children[0] if sv.children else None

        def aplicar(*_):
            if caja is not None and caja.height > sv.height and not getattr(sv, "_touch", None):
                sv.scroll_y = lugar
        aplicar()
        Clock.schedule_once(aplicar, 0)
        if caja is not None:
            caja.bind(height=aplicar)
            sv.bind(height=aplicar)

            def soltar(dt):
                caja.unbind(height=aplicar)
                sv.unbind(height=aplicar)
            Clock.schedule_once(soltar, 1.0)

    def _p_resumen(self, d):
        s = d["snap"]
        sv, caja = pagina()
        self._tarjeta_version(d, caja)
        if s.get("frenado"):
            f = Tarjeta(franja=AMBAR)
            f.add_widget(Texto("El bot está frenado por el límite de pérdida: no abre operaciones nuevas.", 14, AMBAR,
                               negrita=True))
            f.add_widget(Boton("Reanudar", lambda: preguntar("Reanudar", "¿Permitir que el bot vuelva a abrir "
                                                             "operaciones? El límite se mide desde el saldo actual.",
                                                             "Reanudar", lambda: self._accion("reanudar")), col=ACENTO))
            caja.add_widget(f)
        prox = d["bot"].get("proxima_revision")
        seccion(caja, f"Saldo del bot · {d.get('nombre_modo', '')}",
                f"próxima revisión {datetime.fromtimestamp(prox):%H:%M}" if prox else "")
        t = Tarjeta(franja=ACENTO, padding=dp(16), spacing=dp(4))
        fila = BoxLayout(size_hint_y=None, height=dp(44))
        fila.add_widget(Texto(usd(s["saldo"]), 28, negrita=True))
        fila.add_widget(Rotulo(text=pct(s["rendimiento_pct"], 2, True), font_size=sp(15), bold=True,
                              color=color(s["rendimiento_pct"]), size_hint_x=0.45, halign="right", valign="middle"))
        t.add_widget(fila)
        t.add_widget(Texto(f"sobre {usd(s['base'])} de base", 13, GRIS))
        t.add_widget(BoxLayout(size_hint_y=None, height=dp(6)))
        t.add_widget(cuadros((("Resultado cerrado", usd(s["realizado"], 2, True), color(s["realizado"])),
                              ("Resultado abierto", usd(s["abierto"], 2, True), color(s["abierto"])),
                              ("Sin asignar", usd(s["libre"])),
                              ("Operaciones", str(s["resumen_ops"]["n"])))))
        caja.add_widget(t)
        hace = ""
        if d.get("precios_hora"):
            seg = max(0, int(time.time() - d["precios_hora"]))
            hace = f"hace {seg} s" if seg < 120 else f"hace {seg // 60} min"
        seccion(caja, "Mercado ahora", hace)
        g = GridLayout(cols=3, size_hint_y=None, spacing=dp(8)); g.bind(minimum_height=g.setter("height"))
        for a in ("BTC", "ETH", "SOL"):
            x = (s.get("precios") or {}).get(a) or {}
            px, ch = x.get("precio"), x.get("cambio")
            c = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(78), padding=(dp(12), dp(8)), spacing=0)
            fondo(c, PANEL, 12, borde=BORDE)
            c.add_widget(Texto(a, 12, GRIS))
            c.add_widget(Texto(num(px, 2 if (px or 0) >= 100 else 4), 14, negrita=True))
            c.add_widget(Texto(pct(ch, 1, True) if ch is not None else "", 12, color(ch), negrita=True))
            g.add_widget(c)
        caja.add_widget(g)
        ab = s.get("abiertas") or []
        seccion(caja, f"Posiciones abiertas · {len(ab)}" if ab else "Posiciones abiertas")
        t = Tarjeta(franja=VERDE if ab else None, padding=(dp(14), dp(6)), spacing=0)
        for i, f in enumerate(ab):
            if i:
                t.add_widget(separador())
            fila = BoxLayout(size_hint_y=None, height=dp(52))
            izq = BoxLayout(orientation="vertical", padding=(0, dp(6)))
            izq.add_widget(Texto(f"{f['activo']}  ·  {f['estrategia']}", 15, negrita=True))
            izq.add_widget(Texto("Compra" if f["lado"] == "long" else "Venta", 12, GRIS))
            fila.add_widget(izq)
            fila.add_widget(Rotulo(text=usd(f.get("pnl"), 2, True), font_size=sp(15), bold=True, color=color(f.get("pnl")),
                                  size_hint_x=0.6, halign="right", valign="middle"))
            t.add_widget(fila)
        if not ab:
            t.add_widget(Texto("Sin posiciones abiertas. El bot entra cuando aparece una señal.", 14, GRIS,
                               padding=(0, dp(8))))
        caja.add_widget(t)
        meses, _dd = s.get("mensual") or ([], 0)
        hist = (d.get("historial") or {}).get("estrategias") or {}
        base = [b for b in PIL_BASE if b in hist]
        hoy = datetime.now().strftime("%Y-%m")
        seccion(caja, "Resultados por mes", "bot · simulación")
        t = Tarjeta(padding=(dp(14), dp(8)), spacing=0)
        for i, x in enumerate(list(reversed(meses))[:12]):
            vals = [(hist[b].get("mensual") or {}).get(x["mes"]) for b in base]
            sim = sum(vals) / len(vals) if base and x["mes"] < hoy and all(v is not None for v in vals) else None
            fila = GridLayout(cols=3, size_hint_y=None, height=dp(34))
            fila.add_widget(Texto(f"{x['mes'][5:]}/{x['mes'][:4]}", 14))
            fila.add_widget(Texto(pct(x.get("pct"), 1, True), 14, color(x.get("pct")), negrita=True))
            fila.add_widget(Texto(pct(sim, 1, True), 14, GRIS))
            t.add_widget(fila)
        if not meses:
            t.add_widget(Texto("Todavía no hay meses.", 14, GRIS, padding=(0, dp(8))))
        caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _p_posiciones(self, d):
        sv, caja = pagina()

        def px(v):
            return num(v, 2 if (v or 0) >= 100 else 4) if v else "—"
        abiertas = [f for f in d["snap"]["posiciones"] if f["lado"]]
        libres = [f for f in d["snap"]["posiciones"] if not f["lado"]]
        seccion(caja, f"Abiertas · {len(abiertas)}")
        if not abiertas:
            t = Tarjeta(); t.add_widget(Texto("Sin posiciones abiertas. El bot entra cuando aparece una señal.", 14, GRIS))
            caja.add_widget(t)
        for f in abiertas:
            pnl = f.get("pnl")
            t = Tarjeta(franja=VERDE if (pnl or 0) >= 0 else ROJO)
            fila = BoxLayout(size_hint_y=None, height=dp(30))
            fila.add_widget(Texto(f"{f['activo']}  ·  {f['estrategia']}", 16, negrita=True))
            fila.add_widget(Rotulo(text=usd(pnl, 2, True), font_size=sp(16), bold=True, color=color(pnl), size_hint_x=0.6,
                                  halign="right", valign="middle"))
            t.add_widget(fila)
            t.add_widget(Texto(f"{'Compra' if f['lado'] == 'long' else 'Venta'} · monto {usd(f['asignado'])}", 13, GRIS))
            t.add_widget(BoxLayout(size_hint_y=None, height=dp(4)))
            st = -f["riesgo"] if f.get("riesgo") is not None else None
            t.add_widget(cuadros((("Entrada", px(f["entrada"])), ("Precio actual", px(f.get("precio"))),
                                  ("Stop", px(f["stop"])), ("Si toca el stop", usd(st, 2, True), color(st)))))
            caja.add_widget(t)
        if libres:
            seccion(caja, f"Esperando señal · {len(libres)}")
            t = Tarjeta(padding=(dp(14), dp(6)), spacing=0)
            for i, f in enumerate(libres):
                if i:
                    t.add_widget(separador())
                fila = BoxLayout(size_hint_y=None, height=dp(40))
                fila.add_widget(Texto(f"{f['activo']}  ·  {f['estrategia']}", 14))
                fila.add_widget(Rotulo(text=usd(f["asignado"]), font_size=sp(13), color=GRIS, size_hint_x=0.6,
                                      halign="right", valign="middle"))
                t.add_widget(fila)
            caja.add_widget(t)
        seccion(caja, "Cómo se mueve el stop")
        t = Tarjeta()
        t.add_widget(Texto(
            "No hay un precio objetivo fijo. El stop arranca a 2 ATR de la entrada (ATR: lo que se mueve el precio en una "
            "vela típica). Cuando el precio va a favor, el stop lo sigue a 3 ATR (lo revisa cada 10 minutos) y nunca retrocede, así las "
            "ganancias corren. Además, cuando la operación lleva 2 ATR de ganancia, el stop pasa a la entrada más las "
            "comisiones: desde ahí ya no puede cerrar en pérdida. Las estrategias del laboratorio usan sus propias reglas (se "
            "ven en Estrategias).", 13, GRIS))
        caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _p_operaciones(self, d):
        sv, caja = pagina()
        r = d["snap"]["resumen_ops"]
        seccion(caja, "En total")
        t = Tarjeta()
        t.add_widget(cuadros((("Operaciones", str(r["n"])), ("Ganadoras", str(r["ganadas"])),
                              ("Resultado", usd(r["pnl"], 2, True), color(r["pnl"])),
                              ("Acierto", pct(r["ganadas"] / r["n"] * 100, 0) if r["n"] else "—"))))
        caja.add_widget(t)
        ops = d["snap"].get("ultimas_operaciones") or []
        seccion(caja, "Últimas operaciones")
        t = Tarjeta(padding=(dp(14), dp(6)), spacing=0)
        for i, o in enumerate(ops):
            if i:
                t.add_widget(separador())
            fila = BoxLayout(size_hint_y=None, height=dp(56))
            izq = BoxLayout(orientation="vertical", padding=(0, dp(6)))
            izq.add_widget(Texto(f"{o.get('activo')}  ·  {o.get('estrategia')}  ·  "
                                 f"{'compra' if o.get('lado') == 'long' else 'venta'}", 14, negrita=True))
            izq.add_widget(Texto(f"{str(o.get('salida_t', ''))[:16]} · {o.get('motivo', '')}", 12, GRIS))
            fila.add_widget(izq)
            fila.add_widget(Rotulo(text=usd(o.get("pnl"), 2, True), font_size=sp(14), bold=True, color=color(o.get("pnl")),
                                  size_hint_x=0.5, halign="right", valign="middle"))
            t.add_widget(fila)
        if not ops:
            t.add_widget(Texto("Todavía no hay operaciones cerradas.", 14, GRIS, padding=(0, dp(8))))
        caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _p_avisos(self, d):
        sv, caja = pagina()
        al = d.get("alertas") or []
        sl = d.get("sin_leer") or 0
        seccion(caja, f"Avisos · {sl} sin leer" if sl else "Avisos")
        if sl:
            caja.add_widget(Boton("Marcar todos como leídos", lambda: self._accion("avisos_leidos")))
        for a in al:
            t = Tarjeta(franja=ACENTO if not a.get("leida") else None)
            fila = BoxLayout(size_hint_y=None, height=dp(26))
            fila.add_widget(Texto(a["titulo"], 15, negrita=not a.get("leida")))
            fila.add_widget(Rotulo(text=f"{datetime.fromtimestamp(a['hora']):%d/%m %H:%M}", font_size=sp(12), color=GRIS,
                                  size_hint_x=0.4, halign="right", valign="middle"))
            t.add_widget(fila)
            if a.get("texto"):
                t.add_widget(Texto(a["texto"], 14, GRIS))
            caja.add_widget(t)
        if not al:
            t = Tarjeta(); t.add_widget(Texto("No hay avisos.", 14, GRIS)); caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _p_decisiones(self, d):
        sv, caja = pagina()
        dec = getattr(self, "decisiones", None)
        if dec is None or not dec:
            seccion(caja, "Revisiones")
            t = Tarjeta()
            t.add_widget(Texto("Cargando…" if dec is None else "Todavía no hay revisiones registradas. La primera aparece "
                               "después de la próxima revisión del bot.", 14, GRIS))
            caja.add_widget(t); self.cuerpo.add_widget(sv); return
        i = min(getattr(self, "rev_idx", 0), len(dec) - 1)
        x = dec[i]
        h = datetime.fromisoformat(x["hora"])

        def mover(paso):
            self.rev_idx = max(0, min(len(dec) - 1, i + paso)); self._pintar()
        seccion(caja, "Revisión" + (" · la última" if i == 0 else ""), f"{i + 1} de {len(dec)}")
        t = Tarjeta(franja=ACENTO)
        t.add_widget(Texto(f"{h:%d/%m %H:%M} · vela de {x['vela']}", 16, negrita=True))
        ab = sum(1 for it in x["items"] if it["accion"] == "abre")
        ce = sum(1 for it in x["items"] if it["accion"] == "cierra")
        t.add_widget(Texto(f"Abrió {ab} y cerró {ce} posiciones. Revisó {len(x['items'])} partes del capital.", 13, GRIS))
        fila = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        fila.add_widget(Boton("‹ Anterior", lambda: mover(1)))
        fila.add_widget(Boton("Siguiente ›", lambda: mover(-1)))
        t.add_widget(fila)
        caja.add_widget(t)
        seccion(caja, "Qué miró en cada moneda")
        caja.add_widget(Texto("Condiciones que se cumplen (Sí, en verde) y las que faltan (No, en rojo) para abrir.", 13,
                              GRIS, padding=(dp(4), 0)))
        acciones = {"abre": ("Abre", VERDE), "cierra": ("Cierra", ACENTO), "mantiene": ("Mantiene", AMBAR),
                    "no_abre": ("No abre", GRIS), "inactiva": ("Desactivada", GRIS)}
        for it in x["items"]:
            txt, col = acciones.get(it["accion"], (it["accion"], GRIS))
            t = Tarjeta(franja=col if it["accion"] in ("abre", "cierra", "mantiene") else None)
            fila = BoxLayout(size_hint_y=None, height=dp(30))
            fila.add_widget(Texto(f"{it['activo']}  ·  {it.get('estrategia', '')}", 15, negrita=True))
            fila.add_widget(Pildora(txt, col, pos_hint={"center_y": 0.5}))
            t.add_widget(fila)
            conds = it.get("condiciones") or []
            if it["accion"] == "no_abre" and conds:
                t.add_widget(Texto(f"Se cumplen {sum(1 for _, ok in conds if ok)} de {len(conds)} condiciones para "
                                   "entrar:", 13, GRIS))
            elif it["accion"] == "no_abre":
                t.add_widget(Texto("No hubo señal de entrada.", 13, GRIS))
            elif it.get("texto"):
                t.add_widget(Texto(it["texto"][0].upper() + it["texto"][1:] + ".", 13, GRIS))
            for ctext, ok in conds:
                t.add_widget(Texto(("Sí · " if ok else "No · ") + ctext, 13, VERDE if ok else ROJO))
            caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _fila_switch(self, caja, texto, activo, al_cambiar):
        fila = BoxLayout(size_hint_y=None, height=dp(48))
        fila.add_widget(Texto(texto, 15))
        sw = Interruptor(active=bool(activo), size_hint_x=None, width=dp(70))
        sw.bind(active=lambda _s, v: al_cambiar(v))
        fila.add_widget(sw)
        caja.add_widget(fila)

    def _p_control(self, d):
        b = d["bot"]
        sv, caja = pagina()
        txt, col = self._estado_bot()
        prox = b.get("proxima_revision")
        seccion(caja, "Bot")
        t = Tarjeta(franja=col)
        fila = BoxLayout(size_hint_y=None, height=dp(32))
        fila.add_widget(Texto("Estado", 15)); fila.add_widget(Pildora(txt, col, pos_hint={"center_y": 0.5}))
        t.add_widget(fila)
        if prox and b.get("corriendo"):
            t.add_widget(Texto(f"Próxima revisión: {datetime.fromtimestamp(prox):%H:%M}", 13, GRIS))
        if b.get("corriendo"):
            t.add_widget(Boton("Revisar ahora", lambda: self._accion("revisar", "El bot revisa ahora.")))
            t.add_widget(Boton("Detener bot", lambda: preguntar("Detener bot", "¿Detener el bot? Las posiciones abiertas "
                                                                "quedan con su stop en Binance.", "Detener",
                                                                lambda: self._accion("detener")), col=ROJO))
        else:
            t.add_widget(Boton("Iniciar bot", lambda: self._accion("iniciar"), col=ACENTO))
        caja.add_widget(t)
        seccion(caja, "Notificaciones")
        t = Tarjeta()
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
        t = Tarjeta(franja=VERDE if alcanza else AMBAR)
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
        seccion(caja, "Piloto automático")
        t = Tarjeta(franja=ACENTO if s.get("auto") else AMBAR)
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
        seccion(caja, "Estrategias")
        caja.add_widget(Texto("Resultado de cada año y de los últimos 4 semestres con la estrategia siempre prendida, en "
                              "promedio de BTC, ETH y SOL.", 13, GRIS, padding=(dp(4), 0)))
        hist = (d.get("historial") or {}).get("estrategias") or {}
        base_piloto = d.get("piloto_base") or []
        for k, x in hist.items():
            if k in (d.get("retiradas") or []):
                continue
            sem = x.get("semestres") or []
            ua = ((1 + sem[0] / 100) * (1 + sem[1] / 100) - 1) * 100 if len(sem) >= 4 else None
            t = Tarjeta(franja=None if ua is None else VERDE if ua > 0 else ROJO)
            fila = BoxLayout(size_hint_y=None, height=dp(30))
            fila.add_widget(Texto(nombres.get(k, k), 16, negrita=True))
            fila.add_widget(Pildora("Base del piloto" if k in PIL_BASE else ("En el piloto" if k in base_piloto
                                                                           else "Laboratorio"),
                                    ACENTO if k in base_piloto else AMBAR, pos_hint={"center_y": 0.5}))
            t.add_widget(fila)
            if ua is None:
                t.add_widget(Texto("Historial insuficiente para la revisión mensual.", 13, GRIS))
            else:
                t.add_widget(Texto(f"{'Ganó' if ua > 0 else 'Perdió'} {pct(abs(ua), 1)} en los últimos 12 meses: "
                                   f"{'pasa' if ua > 0 else 'no pasa'} la revisión.", 13, VERDE if ua > 0 else ROJO))
            anios = [(str(y), pct((x.get("anios") or {}).get(str(y)), 0, True), color((x.get("anios") or {}).get(str(y))))
                     for y in range(2022, datetime.now().year + 1)]
            t.add_widget(cuadros(anios, cols=3))
            t.add_widget(Texto("Últimos 4 semestres:  " + ("  ·  ".join(pct(v, 0, True) for v in sem) or "—"), 13, GRIS))
            caja.add_widget(t)
        if not hist:
            t = Tarjeta()
            t.add_widget(Texto("El servidor todavía está calculando el historial de las estrategias.", 14, GRIS))
            caja.add_widget(t)
        self.cuerpo.add_widget(sv)

    def _p_servidor(self, d):
        sv, caja = pagina()
        cl = d.get("claves") or {}
        seccion(caja, "Apariencia")
        t = Tarjeta()
        fila = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        fila.add_widget(Boton("Oscuro", lambda: self._cambiar_tema("oscuro"), col=ACENTO if TEMA == "oscuro" else None))
        fila.add_widget(Boton("Claro", lambda: self._cambiar_tema("claro"), col=ACENTO if TEMA == "claro" else None))
        t.add_widget(fila)
        caja.add_widget(t)

        seccion(caja, "Conexión")
        t = Tarjeta()
        t.add_widget(cuadros((("Servidor", f"{self.cliente.host}"), ("Versión", str(d.get("version") or "—")),
                              ("Modo", d.get("nombre_modo") or "—"),
                              ("Claves", f"demo {'sí' if cl.get('demo') else 'no'} · real {'sí' if cl.get('real') else 'no'}"))))
        bc = Boton("Copiar código de conexión", lambda: None)
        bc.bind(on_release=lambda *_: (self._copiar(self.cliente.codigo, bc), avisar("Código de conexión", (
            "Copiado. Pegalo en la otra app (en Windows: \"Ya tengo un código\"). Guardalo como una contraseña: con "
            "este código se controla el bot."))))
        t.add_widget(bc)
        t.add_widget(Boton("Cambiar código de conexión", lambda: self._pantalla_codigo()))
        t.add_widget(Boton("Crear un servidor nuevo en Oracle", self._asistente_inicio))
        caja.add_widget(t)

        seccion(caja, "Cuenta de Binance")
        t = Tarjeta()
        t.add_widget(Texto("El servidor genera la clave y la guarda; la app solo le pasa la API key que te da Binance. "
                           "Empezá por la demo (dinero de prueba).", 13, GRIS))
        t.add_widget(Boton("Conectar Binance demo", lambda: self._pantalla_claves("demo"), col=ACENTO))
        t.add_widget(Boton("Conectar Binance real", lambda: self._pantalla_claves("real")))
        if d.get("modo") != "simulado":
            t.add_widget(Boton("Volver a modo simulado", lambda: preguntar(
                "Modo", "¿Volver a modo simulado? El bot deja de operar en Binance (las posiciones abiertas siguen "
                        "abiertas allá).", "Sí", lambda: self._cambiar_modo("simulado"))))
        caja.add_widget(t)

        seccion(caja, "Riesgo")
        t = Tarjeta()
        t.add_widget(Texto("Riesgo por operación, límite de pérdida (frena el bot si la cuenta pierde ese porcentaje del "
                           "capital del modo) y espera de la orden límite antes de completarla a mercado.", 13, GRIS))
        r = d["riesgo"]
        e1 = Entrada(text=num(r["por_operacion"] * 100, 1), multiline=False, input_filter="float", size_hint_y=None,
                     height=dp(44), font_size=sp(15))
        e2 = Entrada(text=str(int(round(r["limite_perdida"] * 100))), multiline=False, input_filter="int",
                     size_hint_y=None, height=dp(44), font_size=sp(15))
        e4 = Entrada(text=str(int(r.get("espera_limite") or 180)), multiline=False, input_filter="int",
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

        seccion(caja, "Capital del modo")
        t = Tarjeta()
        t.add_widget(Texto("Cuánto dinero de la cuenta usa el bot en el modo actual. Con el piloto encendido, el bot "
                           "reparte el cambio solo.", 13, GRIS))
        e3 = Entrada(text=num((d.get("capital") or {}).get(d["modo"], 100), 2).replace(".", ""), multiline=False,
                     input_filter="float", size_hint_y=None, height=dp(44), font_size=sp(15))
        t.add_widget(e3)
        t.add_widget(Boton("Guardar capital", lambda: self._accion("capital", "Capital guardado.",
                                                                    valor=float(e3.text.replace(",", ".") or 0)),
                           col=ACENTO))
        caja.add_widget(t)
        self._tarjeta_capital_minimo(d, caja)

        lab = d.get("laboratorio") or {}
        est = lab.get("estado") or {}
        seccion(caja, "Laboratorio de estrategias")
        t = Tarjeta()
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
        seccion(caja, "Actualizaciones del servidor")
        t = Tarjeta()
        t.add_widget(Texto("El servidor busca versiones nuevas cada 2 minutos.", 13, GRIS))
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
