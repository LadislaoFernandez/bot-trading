"""Bot de trading — aplicación de escritorio (Windows) con el bot adentro.

  pythonw app.py               abre la ventana y arranca el bot
  pythonw app.py --minimizado  arranca el bot con la ventana oculta (queda el ícono junto a la hora)
"""
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def _log_crash(*exc):
    with open("app_error.log", "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n" + "".join(traceback.format_exception(*exc)))


sys.excepthook = _log_crash
# --datos=CARPETA (solo con --prueba): muestra datos de otra carpeta, p. ej. un ejemplo
DATOS = next((x.split("=", 1)[1] for x in sys.argv if x.startswith("--datos=")), ".")
PRUEBA = "--prueba" in sys.argv

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (QAction, QDesktopServices, QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox,
                               QFrame, QInputDialog, QLineEdit, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QStackedWidget, QSystemTrayIcon, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

import actualizador as AC
import i18n


def _ajustes_iniciales():
    try:
        with open("ajustes.json", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


AJ = _ajustes_iniciales()
i18n.set_lang(AJ.get("idioma", "es"))
from i18n import num, t  # noqa: E402

import app_data as A  # noqa: E402
import claves as CL  # noqa: E402
import config as K  # noqa: E402
import live as LV  # noqa: E402
import mercado as M  # noqa: E402
import paper_trader as PT  # noqa: E402

# ------------------------------------------------------------------ estilo
PALETAS = {
    "oscuro": dict(BG="#0D0D0F", SIDE="#08080A", PANEL="#17171B", PANEL2="#1F1F24", LINE="#2B2B31", TEXT="#F4F4F5",
                   MUTED="#9C9CA6", ACCENT="#FF8A1F", ACCENT_SOFT="#3A2410", GAIN="#3DD68C", LOSS="#FF6B6B",
                   AMBER="#F7C948", ON_ACCENT="#0D0D0F"),
    "claro": dict(BG="#F5F5F4", SIDE="#FFFFFF", PANEL="#FFFFFF", PANEL2="#F0F0EF", LINE="#E4E4E2", TEXT="#18181B",
                  MUTED="#6B6B70", ACCENT="#EA6C00", ACCENT_SOFT="#FFE8D4", GAIN="#16A34A", LOSS="#DC2626",
                  AMBER="#B7791F", ON_ACCENT="#FFFFFF"),
}
TEMA = AJ.get("tema", "oscuro") if AJ.get("tema") in PALETAS else "oscuro"
_P = PALETAS[TEMA]
BG, SIDE, PANEL, PANEL2, LINE = _P["BG"], _P["SIDE"], _P["PANEL"], _P["PANEL2"], _P["LINE"]
TEXT, MUTED, ACCENT, ACCENT_SOFT = _P["TEXT"], _P["MUTED"], _P["ACCENT"], _P["ACCENT_SOFT"]
GAIN, LOSS, AMBER, ON_ACCENT = _P["GAIN"], _P["LOSS"], _P["AMBER"], _P["ON_ACCENT"]
FONT = "Segoe UI Variable Display"
FONT_TXT = "Segoe UI Variable Text"
MONO = "Cascadia Mono"
NB = " "  # espacio que no corta la línea (entre el número y su unidad)


def rgba(hexcol, a):
    h = hexcol.lstrip("#")
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {a})"


QSS = f"""
* {{ font-family: "{FONT_TXT}", "Segoe UI"; color: {TEXT}; }}
QMainWindow, #pagina {{ background: {BG}; }}
QWidget#pagina {{ background: {BG}; }}
#lateral {{ background: {SIDE}; border-right: 1px solid {LINE}; }}
#panel {{ background: {PANEL}; border-radius: 10px; border: 1px solid {LINE}; }}
#panel QLabel, #panel QCheckBox {{ border: none; }}
QLabel {{ background: transparent; }}
QLabel[rol="muted"] {{ color: {MUTED}; }}
QLabel[rol="titulo"] {{ font-family: "{FONT}"; font-size: 15px; font-weight: 600; }}
QLabel[rol="h1"] {{ font-family: "{FONT}"; font-size: 24px; font-weight: 600; }}
QLabel[rol="num"] {{ background: {ACCENT}; color: {ON_ACCENT}; border-radius: 12px; font-weight: 700; font-size: 12px; }}
QPushButton[rol="nav"] {{ text-align: left; padding: 9px 14px; border: none; border-radius: 8px;
    font-size: 14px; color: {MUTED}; background: transparent; }}
QPushButton[rol="nav"]:hover {{ background: {PANEL2}; color: {TEXT}; }}
QPushButton[rol="nav"]:checked {{ background: {ACCENT_SOFT}; color: {ACCENT}; font-weight: 600; }}
QPushButton[rol="accion"] {{ padding: 8px 14px; border-radius: 8px; border: 1px solid {LINE};
    background: {PANEL}; font-size: 13px; }}
QPushButton[rol="accion"]:hover {{ border: 1px solid {ACCENT}; }}
QPushButton[rol="accion"]:disabled {{ color: {MUTED}; }}
QPushButton[rol="primario"] {{ padding: 8px 14px; border-radius: 8px; border: 1px solid {ACCENT};
    background: {ACCENT}; color: {ON_ACCENT}; font-size: 13px; font-weight: 600; }}
QPushButton[rol="primario"]:hover {{ background: {rgba(ACCENT, 0.85)}; }}
QPushButton[rol="primario"]:disabled {{ background: {LINE}; border: 1px solid {LINE}; color: {MUTED}; }}
QPushButton[rol="peligro"] {{ padding: 8px 14px; border-radius: 8px; border: 1px solid {rgba(LOSS, 0.5)};
    background: transparent; color: {LOSS}; font-size: 13px; }}
QPushButton[rol="peligro"]:hover {{ background: {rgba(LOSS, 0.12)}; }}
QPushButton[rol="peligro"]:disabled {{ color: {MUTED}; border: 1px solid {LINE}; }}
QPushButton[rol="rango"] {{ padding: 4px 10px; border-radius: 6px; border: none; color: {MUTED};
    background: transparent; font-size: 12px; }}
QPushButton[rol="rango"]:checked {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QPushButton:focus {{ outline: none; }}
QTableWidget {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px; gridline-color: transparent;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; font-size: 13px; }}
QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {LINE}; }}
QHeaderView::section {{ background: {PANEL}; color: {MUTED}; border: none; border-bottom: 1px solid {LINE};
    padding: 8px; font-size: 12px; }}
QTableCornerButton::section {{ background: {PANEL}; border: none; }}
QPlainTextEdit {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 10px; padding: 10px;
    font-family: "{MONO}", "Consolas"; font-size: 12px; color: {TEXT}; }}
QScrollArea {{ background: {BG}; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {LINE}; border-radius: 4px; min-width: 30px; }}
QMenu {{ background: {PANEL}; border: 1px solid {LINE}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
QToolTip {{ background: {PANEL}; color: {TEXT}; border: 1px solid {LINE}; padding: 6px; }}
QComboBox {{ background: {PANEL2}; border: 1px solid {LINE}; border-radius: 8px; padding: 7px 34px 7px 12px;
    min-width: 220px; font-size: 13px; }}
QComboBox:focus, QComboBox:hover {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right; width: 30px; border: none;
    background: transparent; }}
QComboBox QAbstractItemView::item {{ padding: 6px 10px; min-height: 22px; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {LINE}; selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT}; }}
QCheckBox {{ font-size: 13px; spacing: 8px; }}
QCheckBox[rol="switch"] {{ color: {MUTED}; }}
QCheckBox[rol="switch"]:checked {{ color: {TEXT}; }}
QCheckBox[rol="switch"]::indicator {{ width: 34px; height: 18px; border-radius: 9px; background: {LINE}; }}
QCheckBox[rol="switch"]::indicator:checked {{ background: {ACCENT}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {LINE}; background: {PANEL}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}
QLabel[rol="chip"] {{ border-radius: 9px; padding: 2px 9px; font-size: 12px; }}
QLabel[rol="link"] {{ color: {MUTED}; font-size: 12px; }}
QLabel[rol="link"]:hover {{ color: {ACCENT}; text-decoration: underline; }}
QLineEdit, QDoubleSpinBox {{ background: {PANEL2}; border: 1px solid {LINE}; border-radius: 8px; padding: 6px 10px;
    font-size: 13px; selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; }}
QDoubleSpinBox:disabled {{ color: {MUTED}; }}
QDoubleSpinBox {{ padding: 6px 8px; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; image: none; }}
QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{ width: 0; height: 0; image: none; }}
QPushButton[rol="paso"] {{ min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; padding: 0;
    border-radius: 8px; border: 1px solid {LINE}; background: {PANEL2}; color: {MUTED}; font-size: 17px; font-weight: 600; }}
QPushButton[rol="paso"]:hover {{ border: 1px solid {ACCENT}; color: {ACCENT}; }}
QPushButton[rol="paso"]:pressed {{ background: {ACCENT_SOFT}; }}
QPushButton[rol="paso"]:disabled {{ color: {LINE}; border: 1px solid {LINE}; }}
QLabel[rol="aviso"] {{ font-size: 12px; }}
#actualizacion {{ background: {ACCENT_SOFT}; border: 1px solid {rgba(ACCENT, 0.5)}; border-radius: 10px; }}
#actualizacion QLabel {{ border: none; background: transparent; }}
QLineEdit:focus, QDoubleSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QPushButton[rol="modo"] {{ padding: 12px 16px; border-radius: 10px; border: 1px solid {LINE}; background: {PANEL};
    font-size: 14px; text-align: left; }}
QPushButton[rol="modo"]:hover {{ border: 1px solid {rgba(ACCENT, 0.6)}; }}
QPushButton[rol="modo"]:checked {{ border: 2px solid {ACCENT}; background: {ACCENT_SOFT}; }}
QMessageBox, QInputDialog {{ background: {PANEL}; }}
QMessageBox QPushButton, QInputDialog QPushButton {{ padding: 7px 16px; border-radius: 8px; border: 1px solid {LINE};
    background: {PANEL2}; min-width: 80px; }}
QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {{ border: 1px solid {ACCENT}; }}
"""

DESCRIPCIONES = {
    "BREAKOUT": "Sigue la tendencia. Compra cuando el cierre supera el máximo de las últimas 48 horas con tendencia de "
                "fondo alcista (EMA 50 sobre EMA 200), y vende en corto en el caso contrario. Stop a 2 ATR que sigue al "
                "precio a 3 ATR.",
    "TL": "Espera a que el mercado se comprima y entra cuando vuelve a empujar a favor de la tendencia, como un resorte "
          "que se suelta. Solo compras: tendencia de 4 horas alcista (EMA 10 sobre EMA 55), ADX perdiendo fuerza, squeeze "
          "reciente y momentum que gira hacia arriba. Sale cuando el momentum pasa a negativo o por el stop.",
    "MR": "Para mercados sin tendencia (ADX menor a 20). Compra cuando el precio cae por debajo de la banda inferior de "
          "Bollinger con RSI menor a 30 y vende en corto en el extremo opuesto. Sale al volver a la media, o a las 24 "
          "horas.",
    "RSI2": "Compra caídas cortas y fuertes a favor de la tendencia: precio sobre la EMA 200 y RSI de 2 períodos menor a 10 "
            "(y al revés para ventas en corto). Sale cuando el precio cruza la media de 5 horas, o a las 20 horas.",
    "CRUCE": "Clásica de tendencia: compra cuando la EMA 20 cruza por encima de la EMA 50 con el precio sobre la EMA 200, "
             "y vende en corto en el cruce contrario. Sale en el cruce opuesto o por el stop.",
    "SUPERTREND": "Sigue la dirección del indicador Supertrend (ATR 10, multiplicador 3): compra cuando gira a alcista y "
                  "vende en corto cuando gira a bajista. Stop a 3 ATR que sigue al precio.",
}
COLOR_REGIMEN = {"Tendencia alcista": GAIN, "Tendencia bajista": LOSS, "Lateral": AMBER}
ACCIONES = {"abre": ("Abre", GAIN), "cierra": ("Cierra", ACCENT), "mantiene": ("Mantiene", AMBER),
            "no_abre": ("No abre", MUTED), "inactiva": ("Desactivada", MUTED)}
NIVELES = {"si": ("Conviene ahora", GAIN), "debil": ("Ventaja débil", AMBER), "no": ("No conviene ahora", LOSS),
           "sin_datos": ("Sin datos suficientes", MUTED)}

URL_DEMO_FUTUROS = "https://demo.binance.com/es/futures/BTCUSDT"
URL_DEMO_API = "https://demo.binance.com/es/my/settings/api-management"
URL_REAL_API = "https://www.binance.com/es/my/settings/api-management"

GUIA = [
    ("Probá en modo simulado",
     "La app arranca en Simulado: usa precios reales de Binance pero no manda órdenes. Dejala unos días y mirá Registro "
     "y Operaciones para entender qué hace. Cerrar la ventana no detiene el bot: queda en el ícono junto a la hora.", []),
    ("Entrá a Trading de prueba en Binance",
     "En binance.com, iniciá sesión, tocá el ícono de tu perfil (arriba a la derecha) y elegí Trading de prueba (en "
     "inglés, Demo trading). Entrá a Futuros USD-M y fijate que tengas saldo de prueba en USDT.",
     [("Abrir Futuros en Trading de prueba", URL_DEMO_FUTUROS)]),
    ("Creá la clave de API de prueba",
     "Acá abajo, en Cuenta demo de Binance, tocá Generar clave Ed25519 (la clave pública se copia sola). En la Gestión "
     "de API de Trading de prueba, creá una API eligiendo Autogenerada, pegá la clave pública y confirmá. Copiá la Clave "
     "de API que te muestra Binance, pegala en esta app y tocá Guardar claves.",
     [("Abrir Gestión de API de Trading de prueba", URL_DEMO_API)]),
    ("Probá la conexión",
     "Tocá Probar conexión: muestra el saldo y el tamaño mínimo por orden de cada moneda. Después tocá Probar órdenes: "
     "compra lo mínimo de SOL, pone un stop, lo cancela y cierra. Tarda menos de un minuto.", []),
    ("Elegí el capital y las estrategias",
     "Definí abajo el capital del modo demo. En Estrategias, elegí si el bot cambia de estrategia solo según el mercado "
     "o si las activás vos, y cuánto dinero usa en BTC, ETH y SOL. Binance pide un tamaño mínimo por orden, así que con "
     "montos muy chicos el bot saltea señales.", []),
    ("Pasá a Demo de Binance",
     "Tocá Demo de Binance en Modo de operación. El bot revisa el mercado 20 segundos después del cierre de cada vela "
     "de 1 hora, y cada posición queda con su stop puesto en Binance.", []),
    ("Dinero real, solo después",
     "Recién después de varias semanas en demo. Creá la clave en la Gestión de API de tu cuenta real con permiso de "
     "futuros y SIN permiso de retiros, restringida a la IP de tu conexión. Para activar el modo real hay que escribir "
     "REAL.", [("Abrir Gestión de API de la cuenta real", URL_REAL_API)]),
]


def color_de(v):
    v = round(v or 0, 2)
    return GAIN if v > 0 else LOSS if v < 0 else MUTED


def usd(v, d=2, signo=False):
    return f"{num(v, d, signo)}{NB}USDT"


def pct(v, d=2, signo=False):
    return f"{num(v, d, signo)}{NB}%"


def lbl(texto="", rol=None, size=None, weight=None, family=None, color=None, wrap=False):
    l = QLabel(texto)
    if rol:
        l.setProperty("rol", rol)
    css = []
    if size:
        css.append(f"font-size:{size}px")
    if weight:
        css.append(f"font-weight:{weight}")
    if family:
        css.append(f'font-family:"{family}"')
    if color:
        css.append(f"color:{color}")
    if css:
        l.setStyleSheet(";".join(css))
    if wrap:
        l.setWordWrap(True)
    return l


def boton(texto, rol="accion", accion=None, tip=None):
    b = QPushButton(texto)
    b.setProperty("rol", rol)
    b.setCursor(Qt.PointingHandCursor)
    if accion:
        b.clicked.connect(accion)
    if tip:
        b.setToolTip(tip)
    return b


def panel():
    f = QFrame()
    f.setObjectName("panel")
    return f


def chip(l, texto, col):
    l.setText(texto)
    l.setStyleSheet(f"color:{col}; border:1px solid {rgba(col, 0.6)}; background:{rgba(col, 0.10)};")


def scroll(widget):
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(widget)
    return sa


def con_pasos(sp):
    """Campo numérico con botones − y + propios (más claros que las flechitas de Windows)."""
    # Las flechas propias de Qt se ocultan por estilo (ancho 0). Con setButtonSymbols(NoButtons) y una hoja de estilos,
    # Qt deja el campo de texto con 1 px de ancho y el número no se ve.
    sp.setAlignment(Qt.AlignCenter)
    w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 0, 0, 0); h.setSpacing(4)
    for txt, f in (("−", sp.stepDown), ("+", sp.stepUp)):
        b = QPushButton(txt); b.setProperty("rol", "paso"); b.setCursor(Qt.PointingHandCursor)
        b.setFocusPolicy(Qt.NoFocus); b.setAutoRepeat(True); b.setAutoRepeatDelay(350); b.setAutoRepeatInterval(60)
        b.clicked.connect(f)
        if txt == "−":
            h.addWidget(b); h.addWidget(sp, 1)
        else:
            h.addWidget(b)
    w.campo = sp
    return w


def qss_flechas():
    """Dibuja la flecha de los desplegables con el color del tema y devuelve el estilo que la usa."""
    import tempfile
    carpeta = os.path.join(tempfile.gettempdir(), "bot_trading_iconos")
    os.makedirs(carpeta, exist_ok=True)
    out = ""
    for nombre, col in (("flecha", MUTED), ("flecha_hover", ACCENT)):
        pm = QPixmap(24, 24); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(col), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath(QPointF(6, 9)); path.lineTo(12, 15); path.lineTo(18, 9); p.drawPath(path); p.end()
        ruta = os.path.join(carpeta, f"{nombre}_{TEMA}.png"); pm.save(ruta)
        out += ("QComboBox::down-arrow" + (":hover" if "hover" in nombre else "") +
                f' {{ image: url("{ruta.replace(os.sep, "/")}"); width: 14px; height: 14px; }}\n')
    # tilde de las casillas
    pm = QPixmap(32, 32); pm.fill(Qt.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(ON_ACCENT), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    path = QPainterPath(QPointF(8, 16.5)); path.lineTo(13.5, 22); path.lineTo(24, 10); p.drawPath(path); p.end()
    ruta = os.path.join(carpeta, f"tilde_{TEMA}.png"); pm.save(ruta)
    out += f'QCheckBox::indicator:checked {{ image: url("{ruta.replace(os.sep, "/")}"); }}\n'
    # switch con perilla (encendido, apagado y deshabilitado)
    for nombre, fondo, perilla, x in (("sw_on", ACCENT, "#FFFFFF", 22), ("sw_off", LINE, MUTED, 4),
                                      ("sw_on_dis", rgba(ACCENT, 0.45), "#FFFFFF", 22), ("sw_off_dis", LINE, LINE, 4)):
        pm = QPixmap(76, 40); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing); p.setPen(Qt.NoPen)
        col = QColor(fondo) if fondo.startswith("#") else QColor(ACCENT)
        if "dis" in nombre and "on" in nombre:
            col.setAlpha(115)
        p.setBrush(col); p.drawRoundedRect(QRectF(0, 0, 76, 40), 20, 20)
        p.setBrush(QColor(perilla)); p.drawEllipse(QRectF(x * 2 - 2 if x > 4 else 6, 6, 28, 28)); p.end()
        ruta = os.path.join(carpeta, f"{nombre}_{TEMA}.png"); pm.save(ruta)
        estado = {"sw_on": ":checked", "sw_off": ":unchecked", "sw_on_dis": ":checked:disabled",
                  "sw_off_dis": ":unchecked:disabled"}[nombre]
        out += (f'QCheckBox[rol="switch"]::indicator{estado} {{ image: url("{ruta.replace(os.sep, "/")}"); '
                f'background: transparent; width: 38px; height: 20px; }}\n')
    return out


def preguntar(parent, titulo, texto, si=None, no=None):
    """Pregunta con botones en el idioma de la app. Devuelve True si se eligió la opción afirmativa."""
    m = QMessageBox(parent)
    m.setWindowTitle(titulo)
    m.setText(texto)
    m.setIcon(QMessageBox.Question)
    b_si = m.addButton(si or t("Sí"), QMessageBox.YesRole)
    b_no = m.addButton(no or t("No"), QMessageBox.NoRole)
    m.setDefaultButton(b_no)
    m.exec()
    return m.clickedButton() is b_si


def elegir(parent, titulo, texto, opciones):
    """Pregunta con varias opciones (botones en el idioma de la app). Devuelve el índice elegido, o None si se cerró."""
    m = QMessageBox(parent)
    m.setWindowTitle(titulo)
    m.setText(texto)
    m.setIcon(QMessageBox.Question)
    botones = [m.addButton(o, QMessageBox.RejectRole if i == len(opciones) - 1 else QMessageBox.AcceptRole)
               for i, o in enumerate(opciones)]
    m.setDefaultButton(botones[0])
    m.exec()
    return botones.index(m.clickedButton()) if m.clickedButton() in botones else None


def aviso(parent, titulo, texto, error=False):
    m = QMessageBox(parent)
    m.setWindowTitle(titulo)
    m.setText(texto)
    m.setIcon(QMessageBox.Warning if error else QMessageBox.Information)
    m.addButton(t("Entendido"), QMessageBox.AcceptRole)
    m.exec()


def pedir_texto(parent, titulo, texto):
    d = QInputDialog(parent)
    d.setWindowTitle(titulo)
    d.setLabelText(texto)
    d.setOkButtonText(t("Confirmar"))
    d.setCancelButtonText(t("Cancelar"))
    ok = d.exec()
    return d.textValue(), bool(ok)


def icono_app(color=None, size=64):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color or ACCENT)); p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, size - 4, size - 4)
    pen = QPen(QColor("white"), size * 0.09, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    s = size / 64
    path = QPainterPath(QPointF(14 * s, 44 * s))
    for x, y in [(27, 30), (36, 37), (50, 20)]:
        path.lineTo(x * s, y * s)
    p.drawPath(path)
    p.end()
    return QIcon(pm)


# ------------------------------------------------------------------ inicio con Windows
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NOMBRE = "BotTradingV2"


def inicio_windows(activar=None):
    """Sin argumento: True/False según esté activo (None si no se puede saber). Con argumento: lo activa o lo quita."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            if activar is None:
                try:
                    winreg.QueryValueEx(k, RUN_NOMBRE)
                    return True
                except FileNotFoundError:
                    return False
            if activar:
                winreg.SetValueEx(k, RUN_NOMBRE, 0, winreg.REG_SZ,
                                  f'wscript.exe "{os.path.abspath("iniciar_oculto.vbs")}"')
            else:
                try:
                    winreg.DeleteValue(k, RUN_NOMBRE)
                except FileNotFoundError:
                    pass
            return bool(activar)
    except OSError:
        return None


# ------------------------------------------------------------------ precios en vivo
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

    def _avisar_cambios(self, anterior, nuevo):
        """Revalidación semanal: avisa qué estrategias empezaron a empeorar o se recuperaron."""
        import alertas
        if not anterior or not any("estado" in d for d in anterior.get("estrategias", {}).values()):
            anterior = None  # primer cálculo con esta versión: avisa solo las que hoy empeoran
        for s, cambio in M.comparar(anterior, nuevo):
            rec = nuevo["estrategias"][s].get("reciente", {})
            nombre = M.nombre_estrategia(s)
            sem = datetime.now().strftime("%Y-%W")
            if cambio == "empeora":
                alertas.agregar(f"empeora_{s}_{sem}", "empeora", t("{e} viene empeorando", e=nombre), t(
                    "En los últimos {d} días perdió más de lo que ganó ({pf} en {n} operaciones), aunque en el historial "
                    "completo funciona. El modo automático no la usa hasta que se recupere; si la tenés activada a mano, "
                    "fijate si conviene desactivarla.", d=M.DIAS_RECIENTE, pf=num(rec.get("pf")), n=rec.get("ops")),
                    {"estrategia": s})
            else:
                alertas.agregar(f"recupera_{s}_{sem}", "recupera", t("{e} se recuperó", e=nombre), t(
                    "En los últimos {d} días volvió a ganar más de lo que pierde ({pf} en {n} operaciones).",
                    d=M.DIAS_RECIENTE, pf=num(rec.get("pf")), n=rec.get("ops")), {"estrategia": s})

    def _necesita_historial(self):
        h = self.historial
        from engine import STRATS
        faltan = h and any(s not in h.get("estrategias", {}) for s in STRATS)  # hay estrategias nuevas
        viejo = h and any("estado" not in d for d in h.get("estrategias", {}).values())  # historial de antes de la 1.5
        return self.recalcular.is_set() or not h or faltan or viejo or time.time() - h.get("calculado", 0) > 7 * 86400

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
                    anterior = self.historial
                    M.guardar(h); self.historial = h; self.hist_estado = "listo"
                    self._avisar_cambios(anterior, h)
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
                PT.run_loop(st, stop, None, wake); return
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
            PT.run_loop(st, stop, None, wake, paso=LV.step_live, cliente=br)

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
class RelojVela(QWidget):
    """Anillo con el avance de la vela de 1 hora y la cuenta regresiva a la próxima revisión."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(220, 220)
        self.frac, self.centro, self.sub, self.color = 0.0, "--:--", "", AMBER

    def set(self, frac, centro, sub, color):
        self.frac, self.centro, self.sub, self.color = frac, centro, sub, color
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(14, 14, self.width() - 28, self.height() - 28)
        p.setPen(QPen(QColor(LINE), 10, Qt.SolidLine, Qt.FlatCap))
        p.drawArc(r, 0, 360 * 16)
        p.setPen(QPen(QColor(self.color), 10, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 90 * 16, int(-self.frac * 360 * 16))
        p.setPen(QColor(TEXT))
        f = QFont(FONT); f.setPixelSize(38 if len(self.centro) <= 6 else 26); f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.drawText(QRectF(0, 60, self.width(), 52), Qt.AlignCenter, self.centro)
        f2 = QFont(FONT_TXT); f2.setPixelSize(13)
        p.setFont(f2); p.setPen(QColor(MUTED))
        p.drawText(QRectF(30, 114, self.width() - 60, 60), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, self.sub)
        p.end()


class GraficoCapital(QWidget):
    def __init__(self):
        super().__init__()
        self.pts, self.hover, self.base = [], None, K.INITIAL_CAPITAL
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    def set_puntos(self, pts, base):
        self.pts, self.base = pts, base
        self.update()

    def _geo(self):
        m = dict(l=64, r=16, t=14, b=28)
        w, h = self.width() - m["l"] - m["r"], self.height() - m["t"] - m["b"]
        vals = [v for _, v in self.pts] + [self.base]
        lo, hi = min(vals), max(vals)
        pad = max((hi - lo) * 0.12, 0.5)
        lo, hi = lo - pad, hi + pad
        t0, t1 = self.pts[0][0], self.pts[-1][0]
        if t1 == t0:
            t1 = t0 + 1
        X = lambda x: m["l"] + (x - t0) / (t1 - t0) * w
        Y = lambda v: m["t"] + (1 - (v - lo) / (hi - lo)) * h
        return m, w, h, lo, hi, X, Y

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if len(self.pts) < 2:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap,
                       t("El gráfico aparece después de las primeras revisiones del bot."))
            return
        m, w, h, lo, hi, X, Y = self._geo()
        f = QFont(FONT_TXT); f.setPixelSize(11); p.setFont(f)
        for k in range(5):  # líneas guía
            v = lo + (hi - lo) * k / 4
            y = Y(v)
            p.setPen(QPen(QColor(LINE), 1))
            p.drawLine(QPointF(m["l"], y), QPointF(m["l"] + w, y))
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(0, y - 8, m["l"] - 8, 16), Qt.AlignRight | Qt.AlignVCenter, A.fmt(v))
        yb = Y(self.base)  # capital del modo
        p.setPen(QPen(QColor(MUTED), 1, Qt.DashLine))
        p.drawLine(QPointF(m["l"], yb), QPointF(m["l"] + w, yb))
        last = self.pts[-1][1]
        col = QColor(GAIN if last >= self.base else LOSS)
        path = QPainterPath(QPointF(X(self.pts[0][0]), Y(self.pts[0][1])))
        for x, v in self.pts[1:]:
            path.lineTo(X(x), Y(v))
        area = QPainterPath(path)
        area.lineTo(X(self.pts[-1][0]), m["t"] + h)
        area.lineTo(X(self.pts[0][0]), m["t"] + h)
        g = QLinearGradient(0, m["t"], 0, m["t"] + h)
        c1 = QColor(col); c1.setAlpha(70); c2 = QColor(col); c2.setAlpha(0)
        g.setColorAt(0, c1); g.setColorAt(1, c2)
        p.fillPath(area, QBrush(g))
        p.setPen(QPen(col, 2))
        p.drawPath(path)
        p.setPen(QColor(MUTED))  # fechas
        for x, al in [(self.pts[0][0], Qt.AlignLeft), (self.pts[-1][0], Qt.AlignRight)]:
            xx = X(x)
            rx = QRectF(xx - (0 if al == Qt.AlignLeft else 120), m["t"] + h + 6, 120, 16)
            p.drawText(rx, al | Qt.AlignVCenter, datetime.fromtimestamp(x).strftime("%d/%m %H:%M"))
        if self.hover is not None:
            x, v = self.pts[self.hover]
            xx, y = X(x), Y(v)
            p.setPen(QPen(QColor(MUTED), 1, Qt.DotLine))
            p.drawLine(QPointF(xx, m["t"]), QPointF(xx, m["t"] + h))
            p.setBrush(col); p.setPen(QPen(QColor(BG), 2))
            p.drawEllipse(QPointF(xx, y), 5, 5)
            txt = f"{usd(v)}   {datetime.fromtimestamp(x):%d/%m %H:%M}"
            bw = p.fontMetrics().horizontalAdvance(txt) + 18
            bx = min(max(xx - bw / 2, m["l"]), m["l"] + w - bw)
            p.setBrush(QColor(PANEL2)); p.setPen(QPen(QColor(LINE), 1))
            p.drawRoundedRect(QRectF(bx, m["t"] + 2, bw, 22), 5, 5)
            p.setPen(QColor(TEXT))
            p.drawText(QRectF(bx, m["t"] + 2, bw, 22), Qt.AlignCenter, txt)
        p.end()

    def mouseMoveEvent(self, e):
        if len(self.pts) < 2:
            return
        m, w, h, lo, hi, X, Y = self._geo()
        x = e.position().x()
        self.hover = min(range(len(self.pts)), key=lambda i: abs(X(self.pts[i][0]) - x))
        self.update()

    def leaveEvent(self, _):
        self.hover = None
        self.update()


def tabla(columnas):
    tb = QTableWidget(0, len(columnas))
    tb.setHorizontalHeaderLabels(columnas)
    tb.verticalHeader().setVisible(False)
    tb.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tb.setSelectionBehavior(QAbstractItemView.SelectRows)
    tb.setFocusPolicy(Qt.NoFocus)
    tb.setShowGrid(False)
    tb.setWordWrap(False)
    hh = tb.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.ResizeToContents)
    hh.setStretchLastSection(True)
    hh.setMinimumSectionSize(70)
    hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    hh.setHighlightSections(False)
    tb.verticalHeader().setDefaultSectionSize(38)
    return tb


def celda(tb, r, c, texto, color=None, bold=False, derecha=False):
    it = QTableWidgetItem(texto)
    if color:
        it.setForeground(QColor(color))
    if bold:
        f = it.font(); f.setBold(True); it.setFont(f)
    it.setTextAlignment((Qt.AlignRight if derecha else Qt.AlignLeft) | Qt.AlignVCenter)
    tb.setItem(r, c, it)


# ------------------------------------------------------------------ ventana
class Ventana(QMainWindow):
    def __init__(self, bot, feed, mkt):
        super().__init__()
        self.bot, self.feed, self.mkt, self.saliendo, self.aviso_bandeja = bot, feed, mkt, False, False
        self.rango, self._dec_firma = None, None
        self._montos_sucios, self._llenando_montos = False, False
        self._ultima_notif = None
        self.salir_fn = None
        self.trabajo = {}  # resultados de tareas en segundo plano de la pantalla Configuración
        self.setWindowIcon(QIcon("app_icon.ico") if os.path.exists("app_icon.ico") else icono_app())
        geo = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1440, int(geo.width() * 0.88)), min(920, int(geo.height() * 0.9)))
        self.setMinimumSize(1100, 700)

        raiz = QWidget(); self.setCentralWidget(raiz)
        hl = QHBoxLayout(raiz); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)
        hl.addWidget(self._lateral())
        self.paginas = QStackedWidget(); self.paginas.setObjectName("pagina")
        hl.addWidget(self.paginas, 1)
        for crear in (self._pag_resumen, self._pag_posiciones, self._pag_operaciones, self._pag_estrategias,
                      self._pag_registro, self._pag_configuracion):
            self.paginas.addWidget(crear())
        self.nav_btns[0].setChecked(True)

        self.t_rapido, self.t_datos = QTimer(self), QTimer(self)
        self.t_rapido.timeout.connect(self.tick); self.t_datos.timeout.connect(self.refrescar)
        self.t_rapido.start(1000); self.t_datos.start(3000)
        self.snap = None
        self._pintar_modo()
        self.refrescar()

    # ---------- lateral
    def _lateral(self):
        w = QFrame(); w.setObjectName("lateral"); w.setFixedWidth(232)
        v = QVBoxLayout(w); v.setContentsMargins(14, 20, 14, 16); v.setSpacing(4)
        head = QHBoxLayout(); head.setSpacing(10)
        ic = QLabel(); ic.setPixmap(icono_app().pixmap(32, 32)); head.addWidget(ic, 0, Qt.AlignTop)
        tv = QVBoxLayout(); tv.setSpacing(1)
        tv.addWidget(lbl(t("Bot de trading"), size=16, weight=600, family=FONT))
        self.lbl_modo = lbl("", size=12, wrap=True); tv.addWidget(self.lbl_modo)
        ver = lbl(t("Versión {v}", v=K.VERSION), rol="link"); ver.setCursor(Qt.PointingHandCursor)
        ver.setToolTip(t("Ver qué cambió en cada versión"))
        ver.mousePressEvent = lambda e: self._ver_versiones()
        tv.addWidget(ver)
        head.addLayout(tv, 1)
        v.addLayout(head); v.addSpacing(22)
        self.nav_btns, grupo = [], QButtonGroup(self)
        for i, n in enumerate([t("Resumen"), t("Posiciones"), t("Operaciones"), t("Estrategias"), t("Registro"),
                               t("Configuración")]):
            b = QPushButton(n); b.setProperty("rol", "nav"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            b.setFocusPolicy(Qt.TabFocus)
            b.clicked.connect(lambda _=False, i=i: self.ir_a(i))
            grupo.addButton(b); v.addWidget(b); self.nav_btns.append(b)
        v.addStretch()
        self.box_act = QFrame(); self.box_act.setObjectName("actualizacion")
        ba = QVBoxLayout(self.box_act); ba.setContentsMargins(12, 10, 12, 10); ba.setSpacing(6)
        self.lbl_act_lat = lbl("", size=12, weight=600, wrap=True, color=ACCENT); ba.addWidget(self.lbl_act_lat)
        self.lbl_act_lat_sub = lbl("", rol="muted", size=11, wrap=True); ba.addWidget(self.lbl_act_lat_sub)
        self.btn_act_lat = boton(t("Instalar ahora"), "primario", self._instalar_actualizacion); ba.addWidget(self.btn_act_lat)
        self.box_act.setVisible(False)
        v.addWidget(self.box_act); v.addSpacing(12)
        st = QHBoxLayout(); st.setSpacing(8)
        self.punto = QLabel(); self.punto.setFixedSize(10, 10)
        st.addWidget(self.punto); self.lbl_estado = lbl("", size=13, weight=600); st.addWidget(self.lbl_estado, 1)
        v.addLayout(st)
        self.lbl_estado_sub = lbl("", rol="muted", size=12, wrap=True)
        v.addWidget(self.lbl_estado_sub); v.addSpacing(10)
        self.btn_revisar = boton(t("Revisar ahora"), accion=self.bot.revisar_ahora,
                                 tip=t("Hace una revisión fuera de horario. Solo opera si hay velas nuevas cerradas."))
        self.btn_bot = boton("", accion=self.alternar_bot)
        v.addWidget(self.btn_revisar); v.addWidget(self.btn_bot)
        return w

    def ir_a(self, i):
        self.nav_btns[i].setChecked(True)
        self.paginas.setCurrentIndex(i)

    def _pagina(self, titulo, sub=None):
        w = QWidget(); w.setObjectName("pagina")
        v = QVBoxLayout(w); v.setContentsMargins(28, 24, 28, 24); v.setSpacing(16)
        v.addWidget(lbl(titulo, rol="h1"))
        if sub:
            v.addWidget(lbl(sub, rol="muted", size=13, wrap=True))
        return w, v

    # ---------- resumen
    def _pag_resumen(self):
        w, v = self._pagina(t("Resumen"), t(
            "Cuánto tiene el bot, cuándo es la próxima revisión, cómo viene la cuenta y lo último que hizo."))
        hero = panel(); hl = QHBoxLayout(hero); hl.setContentsMargins(20, 16, 24, 16); hl.setSpacing(28)
        self.reloj = RelojVela(); hl.addWidget(self.reloj)
        sv = QVBoxLayout(); sv.setSpacing(4); sv.addStretch()
        sv.addWidget(lbl(t("Saldo del bot"), rol="muted", size=13))
        self.lbl_saldo = lbl("", size=44, weight=600, family=FONT); sv.addWidget(self.lbl_saldo)
        self.lbl_rend = lbl("", size=14, wrap=True); sv.addWidget(self.lbl_rend); sv.addSpacing(14)
        g = QGridLayout(); g.setHorizontalSpacing(26); g.setVerticalSpacing(2)
        self.kpi = {}
        for c, (k, titulo, tip) in enumerate([
                ("real", t("Resultado cerrado"), t("Lo ganado o perdido en las operaciones ya cerradas.")),
                ("abierto", t("Resultado abierto"), t("Lo que van ganando o perdiendo las posiciones abiertas ahora.")),
                ("libre", t("Sin asignar"), t("Capital del modo que no está asignado a ninguna estrategia.")),
                ("nops", t("Operaciones cerradas"), t("Cantidad de operaciones cerradas en este modo."))]):
            x = lbl(titulo, rol="muted", size=12); x.setToolTip(tip)
            val = lbl("", size=17, weight=600); val.setToolTip(tip)
            g.addWidget(x, 0, c, Qt.AlignBottom); g.addWidget(val, 1, c)
            self.kpi[k] = val
        sv.addLayout(g); sv.addStretch()
        hl.addLayout(sv, 1)
        mk = QVBoxLayout(); mk.setSpacing(10); mk.addStretch()
        mk.addWidget(lbl(t("Mercado ahora"), rol="muted", size=13))
        self.lbl_precios = {}
        for a in K.SYMBOLS:
            row = QHBoxLayout(); row.setSpacing(10)
            row.addWidget(lbl(a, size=14, weight=600)); row.addStretch()
            pl, cl = lbl("—", size=14, family=FONT), lbl("", size=12)
            cl.setMinimumWidth(96); cl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(pl); row.addWidget(cl)
            self.lbl_precios[a] = (pl, cl); mk.addLayout(row)
        self.lbl_precios_upd = lbl("", rol="muted", size=11, wrap=True)
        mk.addWidget(self.lbl_precios_upd); mk.addStretch()
        mkw = QWidget(); mkw.setLayout(mk); mkw.setFixedWidth(270)
        hl.addWidget(mkw)
        v.addWidget(hero)

        gp = panel(); gv = QVBoxLayout(gp); gv.setContentsMargins(18, 14, 18, 12)
        gh = QHBoxLayout(); gh.addWidget(lbl(t("Evolución del saldo"), rol="titulo")); gh.addStretch()
        self.rangos = QButtonGroup(self)
        for n, seg in [(t("24 h"), 86400), (t("7 días"), 7 * 86400), (t("30 días"), 30 * 86400), (t("Todo"), None)]:
            b = QPushButton(n); b.setProperty("rol", "rango"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, s=seg: self._set_rango(s))
            self.rangos.addButton(b); gh.addWidget(b)
            if seg is None:
                b.setChecked(True)
        gv.addLayout(gh)
        self.grafico = GraficoCapital(); gv.addWidget(self.grafico, 1)
        v.addWidget(gp, 1)

        bottom = QHBoxLayout(); bottom.setSpacing(16)
        pa = panel(); pav = QVBoxLayout(pa); pav.setContentsMargins(18, 14, 18, 14)
        pav.addWidget(lbl(t("Posiciones abiertas"), rol="titulo"))
        self.box_abiertas = QVBoxLayout(); self.box_abiertas.setSpacing(6); pav.addLayout(self.box_abiertas); pav.addStretch()
        uo = panel(); uov = QVBoxLayout(uo); uov.setContentsMargins(18, 14, 18, 14)
        uov.addWidget(lbl(t("Últimas operaciones"), rol="titulo"))
        self.box_ultimas = QVBoxLayout(); self.box_ultimas.setSpacing(6); uov.addLayout(self.box_ultimas); uov.addStretch()
        bottom.addWidget(pa, 1); bottom.addWidget(uo, 1)
        v.addLayout(bottom)
        return w

    def _set_rango(self, seg):
        self.rango = seg
        self._pintar_grafico()

    # ---------- posiciones
    def _pag_posiciones(self):
        w, v = self._pagina(t("Posiciones"), t(
            "Cada estrategia activa opera por separado en cada moneda con el monto que le asignaste en Estrategias, y "
            "reinvierte sus propias ganancias."))
        self.tab_pos = tabla([t("Moneda"), t("Estrategia"), t("Monto asignado"), t("Capital actual"), t("Estado"),
                              t("Entrada"), t("Precio"), t("Stop"), t("Distancia al stop"), t("Tamaño"),
                              t("Resultado abierto"), t("Abierta hace")])
        v.addWidget(self.tab_pos, 1)
        return w

    # ---------- operaciones
    def _pag_operaciones(self):
        w, v = self._pagina(t("Operaciones"), t(
            "Todas las operaciones cerradas en este modo, con su resultado y el motivo de salida."))
        fila = QHBoxLayout(); fila.setSpacing(36)
        self.op_stats = {}
        for k, x in [("n", t("Cerradas")), ("pct", t("Ganadoras")), ("pnl", t("Resultado total")), ("mejor", t("Mejor")),
                     ("peor", t("Peor"))]:
            c = QVBoxLayout(); c.setSpacing(2)
            c.addWidget(lbl(x, rol="muted", size=12)); l = lbl("—", size=20, weight=600, family=FONT); c.addWidget(l)
            self.op_stats[k] = l; fila.addLayout(c)
        fila.addStretch()
        fila.addWidget(boton(t("Abrir archivo de operaciones"), accion=lambda: self._abrir(K.TRADES_FILE)), 0, Qt.AlignBottom)
        v.addLayout(fila)
        self.tab_ops = tabla([t("Cierre"), t("Moneda"), t("Estrategia"), t("Dirección"), t("Entrada"), t("Salida"),
                              t("Motivo"), t("Resultado"), t("Capital después")])
        vacio = panel(); vl = QVBoxLayout(vacio); vl.setContentsMargins(24, 24, 24, 24)
        vl.addWidget(lbl(t("Todavía no hay operaciones cerradas. Aparecen acá en cuanto el bot cierre la primera, con su "
                           "resultado y el motivo de salida."), rol="muted", size=14, wrap=True)); vl.addStretch()
        self.stack_ops = QStackedWidget(); self.stack_ops.addWidget(vacio); self.stack_ops.addWidget(self.tab_ops)
        v.addWidget(self.stack_ops, 1)
        return w

    # ---------- registro
    def _pag_registro(self):
        w, v = self._pagina(t("Registro"), t("En cada revisión el bot anota qué decidió en cada parte del capital y por qué."))
        h = QHBoxLayout(); h.setSpacing(10)
        h.addWidget(lbl(t("Revisión"), rol="muted", size=13)); self.cmb_rev = QComboBox(); self.cmb_rev.setMinimumWidth(300)
        h.addWidget(self.cmb_rev)
        self.cmb_rev.currentIndexChanged.connect(self._pintar_decision)
        h.addStretch()
        h.addWidget(boton(t("Abrir carpeta del bot"), accion=lambda: self._abrir(".")))
        h.addWidget(boton(t("Abrir archivo de registro"), accion=lambda: self._abrir(K.LOG_FILE)))
        v.addLayout(h)
        cont = QWidget(); cont.setObjectName("pagina"); self.box_dec = QVBoxLayout(cont)
        self.box_dec.setContentsMargins(0, 0, 8, 0); self.box_dec.setSpacing(8)
        v.addWidget(scroll(cont), 3)
        v.addWidget(lbl(t("Registro completo"), rol="titulo"))
        self.txt_log = QPlainTextEdit(); self.txt_log.setReadOnly(True); self.txt_log.setMinimumHeight(150)
        v.addWidget(self.txt_log, 2)
        self._log_n = None
        return w

    def _llenar_decisiones(self):
        dec = self.snap["decisiones"]
        firma = (len(dec), dec[0]["hora"] if dec else None)
        if firma == self._dec_firma:
            return
        estaba_en_ultima = self.cmb_rev.currentIndex() <= 0
        sel = self.cmb_rev.currentText()
        self._dec_firma, self._dec = firma, dec
        self.cmb_rev.blockSignals(True); self.cmb_rev.clear()
        for d in dec:
            x = datetime.fromisoformat(d["hora"])
            self.cmb_rev.addItem(t("{h}, vela de {v}", h=f"{x:%d/%m %H:%M}", v=d["vela"]))
        idx = 0 if estaba_en_ultima else max(0, self.cmb_rev.findText(sel))
        self.cmb_rev.setCurrentIndex(idx); self.cmb_rev.blockSignals(False)
        self._pintar_decision()

    def _pintar_decision(self):
        self._vaciar(self.box_dec)
        dec = getattr(self, "_dec", [])
        if not dec:
            self.box_dec.addWidget(lbl(t("Todavía no hay revisiones registradas con el detalle de cada decisión. La "
                                         "primera aparece después de la próxima revisión del bot."), rol="muted", size=14,
                                       wrap=True))
            self.box_dec.addStretch(); return
        d = dec[max(0, self.cmb_rev.currentIndex())]
        abiertas = sum(1 for it in d["items"] if it["accion"] == "abre")
        cerradas = sum(1 for it in d["items"] if it["accion"] == "cierra")
        self.box_dec.addWidget(lbl(t("En esta revisión el bot abrió {a} y cerró {c} posiciones. Revisó {n} partes del "
                                     "capital.", a=abiertas, c=cerradas, n=len(d["items"])), size=14, wrap=True))
        for it in d["items"]:
            card = panel(); hl = QHBoxLayout(card); hl.setContentsMargins(16, 12, 16, 12); hl.setSpacing(18)
            izq = QVBoxLayout(); izq.setSpacing(4)
            izq.addWidget(lbl(it["activo"], size=15, weight=600))
            izq.addWidget(lbl(M.nombre_estrategia(it["clave"]) if it.get("clave") in PT.NOMBRES else it["estrategia"],
                              rol="muted", size=12, wrap=True))
            txt, col = ACCIONES.get(it["accion"], (it["accion"], MUTED))
            c = lbl("", rol="chip"); chip(c, t(txt), col)
            izq.addWidget(c, 0, Qt.AlignLeft); izq.addStretch()
            iz = QWidget(); iz.setLayout(izq); iz.setFixedWidth(180); hl.addWidget(iz)
            der = QVBoxLayout(); der.setSpacing(3)
            conds = it.get("condiciones", [])
            if it["accion"] == "no_abre" and conds:  # el chip ya dice "No abre": acá solo el detalle
                ok_n = sum(1 for _, ok in conds if ok)
                principal = t("Se cumplen {c} de {n} condiciones para entrar:", c=ok_n, n=len(conds))
            elif it["accion"] == "no_abre":
                principal = t("No hubo señal de entrada.")
            else:
                x = it["texto"]
                principal = (x[0].upper() + x[1:] + ".") if x else ""
            der.addWidget(lbl(principal, size=13, wrap=True))
            for ctext, ok in conds:
                der.addWidget(lbl(("✓  " if ok else "✗  ") + ctext, size=12, color=GAIN if ok else LOSS, wrap=True))
            hl.addLayout(der, 1)
            self.box_dec.addWidget(card)
        self.box_dec.addStretch()

    # ---------- estrategias
    def _pag_estrategias(self):
        w, v = self._pagina(t("Estrategias"), t(
            "El mercado de cada moneda leído cada 5 minutos, cómo le fue a cada estrategia desde 2022 en momentos parecidos "
            "al actual, y qué estrategias usa el bot y con cuánto dinero."))
        inner = QWidget(); inner.setObjectName("pagina"); iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 10, 0); iv.setSpacing(12)
        self.pan_avisos = QFrame(); self.pan_avisos.setObjectName("actualizacion")
        pav_ = QVBoxLayout(self.pan_avisos); pav_.setContentsMargins(16, 12, 16, 12); pav_.setSpacing(8)
        ha_ = QHBoxLayout(); ha_.addWidget(lbl(t("Avisos"), rol="titulo")); ha_.addStretch()
        ha_.addWidget(boton(t("Marcar como leídos"), accion=self._leer_avisos)); pav_.addLayout(ha_)
        self.box_avisos = QVBoxLayout(); self.box_avisos.setSpacing(8); pav_.addLayout(self.box_avisos)
        self.pan_avisos.setVisible(False); iv.addWidget(self.pan_avisos)
        self._avisos_firma, self._avisos_vistos = None, None
        h = QHBoxLayout(); h.addWidget(lbl(t("Mercado ahora"), rol="titulo")); h.addStretch()
        self.lbl_mkt_upd = lbl("", rol="muted", size=12); h.addWidget(self.lbl_mkt_upd); iv.addLayout(h)
        fila = QHBoxLayout(); fila.setSpacing(12); self.mkt_ui = {}
        for a in K.SYMBOLS:
            p = panel(); pv = QVBoxLayout(p); pv.setContentsMargins(16, 14, 16, 14); pv.setSpacing(5)
            top = QHBoxLayout(); top.addWidget(lbl(a, size=18, weight=600, family=FONT)); top.addStretch()
            c = lbl("", rol="chip"); chip(c, t("Leyendo…"), MUTED); top.addWidget(c); pv.addLayout(top)
            l1, l2, l3 = (lbl("", rol="muted", size=12, wrap=True) for _ in range(3))
            for x in (l1, l2, l3):
                pv.addWidget(x)
            pv.addSpacing(4)
            res = lbl("", size=13, wrap=True); pv.addWidget(res)
            rec = lbl("", size=13, wrap=True); pv.addWidget(rec); pv.addStretch()
            self.mkt_ui[a] = (c, (l1, l2, l3), res, rec); fila.addWidget(p, 1)
        iv.addLayout(fila); iv.addSpacing(6)

        # modo de selección
        pa = panel(); pav = QVBoxLayout(pa); pav.setContentsMargins(18, 14, 18, 14); pav.setSpacing(8)
        ha = QHBoxLayout(); ha.addWidget(lbl(t("Cómo se eligen las estrategias"), rol="titulo")); ha.addStretch()
        self.sw_auto = QCheckBox(t("Automático según el mercado")); self.sw_auto.setProperty("rol", "switch")
        self.sw_auto.setCursor(Qt.PointingHandCursor); self.sw_auto.clicked.connect(self._cambiar_auto)
        ha.addWidget(self.sw_auto); pav.addLayout(ha)
        pav.addWidget(lbl(t("Con el switch encendido, el bot elige solo qué estrategias usar en cada moneda: en cada "
                            "revisión lee el tipo de mercado (si se mantiene 3 horas seguidas) y usa hasta 2 estrategias que "
                            "en ese tipo de mercado ganaron al menos 1,10 veces lo que perdieron. Vos solo elegís cuánto "
                            "dinero usa en cada moneda. Con el switch apagado, activás las estrategias a mano."),
                          rol="muted", size=12, wrap=True))
        self.lbl_auto = lbl("", size=13, wrap=True); pav.addWidget(self.lbl_auto)
        iv.addWidget(pa)

        # montos
        pm = panel(); pmv = QVBoxLayout(pm); pmv.setContentsMargins(18, 14, 18, 14); pmv.setSpacing(8)
        self.lbl_montos_tit = lbl(t("Dinero por estrategia y moneda"), rol="titulo"); pmv.addWidget(self.lbl_montos_tit)
        self.lbl_montos_ayuda = lbl("", rol="muted", size=12, wrap=True); pmv.addWidget(self.lbl_montos_ayuda)
        self.w_auto_montos = QWidget(); ham = QHBoxLayout(self.w_auto_montos); ham.setContentsMargins(0, 4, 0, 4)
        ham.setSpacing(10); self.montos_auto = {}
        for a in K.SYMBOLS:
            ham.addWidget(lbl(a, size=13, weight=600))
            sp = QDoubleSpinBox(); sp.setRange(0, 1_000_000); sp.setDecimals(2); sp.setSingleStep(10)
            sp.setSuffix(NB + "USDT"); sp.setMinimumWidth(130); sp.setKeyboardTracking(False)
            sp.valueChanged.connect(self._montos_editados)
            ham.addWidget(con_pasos(sp)); ham.addSpacing(10); self.montos_auto[a] = sp
        ham.addStretch(); pmv.addWidget(self.w_auto_montos)
        self.lbl_montos = lbl("", size=13, wrap=True); pmv.addWidget(self.lbl_montos)
        self.w_botones_montos = QWidget(); hb = QHBoxLayout(self.w_botones_montos); hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(8)
        self.btn_guardar_montos = boton(t("Guardar montos"), "primario", self._guardar_montos)
        hb.addWidget(self.btn_guardar_montos)
        hb.addWidget(boton(t("Repartir en partes iguales"), accion=self._repartir_montos,
                           tip=t("Divide todo el saldo disponible en partes iguales.")))
        self.btn_deshacer_montos = boton(t("Deshacer cambios"), accion=lambda: self._llenar_montos(forzar=True))
        hb.addWidget(self.btn_deshacer_montos); hb.addStretch()
        pmv.addWidget(self.w_botones_montos)
        self.lbl_minimos = lbl("", rol="muted", size=12, wrap=True); pmv.addWidget(self.lbl_minimos)
        iv.addWidget(pm); iv.addSpacing(6)

        # laboratorio
        pl = panel(); plv = QVBoxLayout(pl); plv.setContentsMargins(18, 14, 18, 14); plv.setSpacing(8)
        hl_ = QHBoxLayout(); hl_.addWidget(lbl(t("Laboratorio de estrategias"), rol="titulo")); hl_.addStretch()
        self.sw_lab = QCheckBox(t("Activo")); self.sw_lab.setProperty("rol", "switch"); self.sw_lab.setCursor(Qt.PointingHandCursor)
        self.sw_lab.clicked.connect(self._cambiar_lab); hl_.addWidget(self.sw_lab); plv.addLayout(hl_)
        plv.addWidget(lbl(t(
            "Busca estrategias nuevas combinando las piezas que ya usa el bot (filtros de tendencia, disparos de entrada, "
            "salidas y stops). Las elige con velas de 2022 a 2024 y las prueba con velas de 2025 a hoy, que no usó para "
            "elegirlas: solo propone las que ganan en esa prueba en al menos 2 de las 3 monedas y en 3 de cada 4 años. "
            "Corre en segundo plano cada 6 horas durante 20 minutos, con prioridad baja. Las candidatas nunca operan "
            "solas: vos decidís si agregarlas."), rol="muted", size=12, wrap=True))
        hb_ = QHBoxLayout(); hb_.setSpacing(8)
        self.lbl_lab = lbl("", size=13, wrap=True); hb_.addWidget(self.lbl_lab, 1)
        self.btn_lab = boton(t("Buscar ahora"), accion=lambda: self._lanzar_lab(manual=True)); hb_.addWidget(self.btn_lab)
        plv.addLayout(hb_)
        self.box_cand = QVBoxLayout(); self.box_cand.setSpacing(10); plv.addLayout(self.box_cand)
        iv.addWidget(pl); iv.addSpacing(6)
        self._cand_firma = None

        h = QHBoxLayout(); h.addWidget(lbl(t("Estrategias disponibles"), rol="titulo")); h.addStretch()
        self.lbl_hist = lbl("", rol="muted", size=12); h.addWidget(self.lbl_hist)
        self.btn_hist = boton(t("Recalcular historial"), accion=self.mkt.recalcular.set)
        h.addWidget(self.btn_hist); iv.addLayout(h)
        self.estr_ui, self.montos, self.montos_w, self.filas_monto = {}, {}, {}, {}
        for k, nombre in PT.NOMBRES.items():
            p = panel(); pv = QVBoxLayout(p); pv.setContentsMargins(18, 14, 18, 14); pv.setSpacing(8)
            top = QHBoxLayout(); top.setSpacing(10); top.addWidget(lbl(M.nombre_estrategia(k), rol="titulo"))
            rec = lbl("", rol="chip"); top.addWidget(rec); top.addStretch()
            sw = QCheckBox(t("Activa")); sw.setProperty("rol", "switch"); sw.setCursor(Qt.PointingHandCursor)
            sw.clicked.connect(lambda checked, k=k: self._cambiar_estrategia(k, checked)); top.addWidget(sw)
            pv.addLayout(top)
            if k in DESCRIPCIONES:
                desc = t(DESCRIPCIONES[k])
            else:
                import catalogo
                dd = catalogo.DEFINICIONES[k]
                desc = catalogo.descripcion(dd, i18n.LANG)
                origen = t("Agregada por vos desde el laboratorio.") if dd.get("_origen") == "mis_estrategias" else \
                    t("Estrategia del catálogo de la app.")
                desc += " " + origen
            pv.addWidget(lbl(desc, size=13, wrap=True))
            porque = lbl("", size=13, wrap=True); pv.addWidget(porque)
            g = QGridLayout(); g.setHorizontalSpacing(28); g.setVerticalSpacing(2); celdas = {}
            for c, r in enumerate(M.REGIMENES + ["Total", "Reciente"]):
                tit = (t("Todo el período") if r == "Total" else t("Últimos {d} días", d=M.DIAS_RECIENTE)
                       if r == "Reciente" else t(r))
                g.addWidget(lbl(tit, rol="muted", size=12), 0, c)
                x = lbl("—", size=13); g.addWidget(x, 1, c); celdas[r] = x
            g.setColumnStretch(5, 1); pv.addLayout(g)
            mw = QWidget(); mh = QHBoxLayout(mw); mh.setContentsMargins(0, 0, 0, 0); mh.setSpacing(10)
            mh.addWidget(lbl(t("Monto por moneda"), rol="muted", size=12))
            for a in K.SYMBOLS:
                mh.addSpacing(8); mh.addWidget(lbl(a, size=13, weight=600))
                sp = QDoubleSpinBox(); sp.setRange(0, 1_000_000); sp.setDecimals(2); sp.setSingleStep(5)
                sp.setSuffix(NB + "USDT"); sp.setMinimumWidth(130); sp.setKeyboardTracking(False)
                sp.valueChanged.connect(self._montos_editados)
                cw = con_pasos(sp); mh.addWidget(cw); self.montos[(k, a)] = sp; self.montos_w[(k, a)] = cw
            mh.addStretch(); pv.addWidget(mw); self.filas_monto[k] = mw
            import catalogo
            if catalogo.DEFINICIONES.get(k, {}).get("_origen") == "mis_estrategias":
                hq = QHBoxLayout(); hq.addStretch()
                hq.addWidget(boton(t("Proponer para todos"), accion=lambda _=False, k=k: self._proponer(catalogo.DEFINICIONES[k])))
                hq.addWidget(boton(t("Quitar de mis estrategias"), "peligro", lambda _=False, k=k: self._quitar_propia(k)))
                pv.addLayout(hq)
            self.estr_ui[k] = (sw, rec, porque, celdas); iv.addWidget(p)
        iv.addWidget(lbl(t("Cada celda muestra el factor de ganancia (lo ganado dividido lo perdido: más de 1 es positivo) y "
                           "cuántas operaciones hubo, sumando BTC, ETH y SOL con el mismo riesgo y comisiones que usa el "
                           "bot. Con menos de {n} operaciones el dato no es confiable.", n=M.MIN_OPS),
                         rol="muted", size=12, wrap=True))
        iv.addStretch()
        v.addWidget(scroll(inner), 1)
        return w

    def _llenar_estrategias(self):
        mk, hist, ahora = self.mkt, self.mkt.historial, time.time()
        if mk.actualizado:
            self.lbl_mkt_upd.setText(t("Actualizado hace {d}", d=A.fmt_dur(ahora - mk.actualizado)) if ahora - mk.actualizado >= 60
                                     else t("Actualizado hace menos de 1 minuto"))
        elif mk.error:
            self.lbl_mkt_upd.setText(t("No se pudo leer el mercado. Reintenta en 5 minutos."))
        regimenes = {}
        for a, (c, lineas, res, rec) in self.mkt_ui.items():
            an = mk.analisis.get(a)
            if not an:
                continue
            regimenes[a] = an["regimen"]
            chip(c, t(an["regimen"]), COLOR_REGIMEN[an["regimen"]])
            pos = an["pos_rango48"]
            zona = t("cerca del máximo") if pos > 80 else t("cerca del mínimo") if pos < 20 else t("en la mitad")
            lineas[0].setText(t("Precio {p}  ·  {v} en 24 h", p=A.fmt_precio(an["precio"]), v=pct(an["var24"], 1, True)))
            lineas[1].setText(t("ADX {a}  ·  RSI {r}  ·  tendencia de 4 h {d}", a=num(an["adx"], 1), r=num(an["rsi"], 0),
                                d=t(an["tendencia_4h"])))
            lineas[2].setText(t("Rango de 48 h: {z} ({p})", z=zona, p=pct(pos, 0)))
            res.setText(an["resumen"])
            ranking = M.recomendar(hist, an["regimen"])
            mejor = next((f for f in ranking if f["recomendable"]), None)
            if not hist:
                rec.setText(t("La recomendación aparece cuando termine de calcularse el historial."))
                rec.setStyleSheet(f"font-size:13px; color:{MUTED}")
            elif mejor:
                rec.setText(t("Mejor para este mercado: {e}. Ganó {pf} veces lo que perdió, en {n} operaciones.",
                              e=M.nombre_estrategia(mejor["estrategia"]), pf=num(mejor["pf"]), n=mejor["ops"]))
                rec.setStyleSheet(f"font-size:13px; font-weight:600; color:{GAIN}")
            else:
                rec.setText(t("Ninguna estrategia tuvo una ventaja clara en este tipo de mercado. Conviene operar con "
                              "cautela o no operar."))
                rec.setStyleSheet(f"font-size:13px; font-weight:600; color:{AMBER}")
        if mk.hist_estado == "calculando":
            f, x = mk.hist_prog
            self.lbl_hist.setText(t("Calculando historial ({p}): {x}", p=pct(f * 100, 0), x=x))
        elif mk.hist_estado == "error":
            self.lbl_hist.setText(t("No se pudo calcular el historial:") + " " + mk.hist_prog[1])
        elif hist:
            d = hist["desde"]
            self.lbl_hist.setText(t("Historial calculado el {f}, con velas desde el {d}",
                                    f=f"{datetime.fromtimestamp(hist['calculado']):%d/%m %H:%M}", d=f"{d[8:10]}/{d[5:7]}/{d[:4]}"))
        self.btn_hist.setEnabled(mk.hist_estado != "calculando")
        activas, auto = self.snap["activas"], self.snap.get("auto")
        self.sw_auto.blockSignals(True); self.sw_auto.setChecked(bool(auto)); self.sw_auto.blockSignals(False)
        self.sw_auto.setText(t("Automático según el mercado") if auto else t("Manual"))
        por_moneda = self.snap.get("activas_moneda") or {}
        if auto:
            ae = self.snap.get("auto_estado") or {}
            sel, regs = ae.get("seleccion", {}), ae.get("regimen", {})
            if not sel:
                self.lbl_auto.setText(t("Modo automático encendido. El bot elige las estrategias en la próxima revisión."))
            else:
                partes = []
                for a in K.SYMBOLS:
                    ss = sel.get(a, [])
                    nom = ", ".join(M.nombre_estrategia(x) for x in ss) if ss else t("ninguna (no abre operaciones nuevas)")
                    partes.append(t("{a} ({r}): {e}", a=a, r=t(regs.get(a) or "—").lower(), e=nom))
                self.lbl_auto.setText(t("Ahora usa:") + " " + "; ".join(partes) + ".")
            self.lbl_auto.setStyleSheet(f"font-size:13px; color:{ACCENT}")
        else:
            self.lbl_auto.setText(t("Modo manual: usa las estrategias que actives abajo, con los montos que elijas."))
            self.lbl_auto.setStyleSheet(f"font-size:13px; color:{TEXT}")
        for k, (sw, rec, porque, celdas) in self.estr_ui.items():
            if auto:
                usan = [a for a in K.SYMBOLS if k in por_moneda.get(a, [])]
                sw.blockSignals(True); sw.setChecked(bool(usan)); sw.blockSignals(False)
                sw.setText(t("En uso en {m}", m=", ".join(usan)) if usan else t("Sin usar"))
                sw.setEnabled(False); sw.setToolTip(t("En modo automático el bot elige las estrategias."))
            else:
                sw.blockSignals(True); sw.setChecked(k in activas); sw.blockSignals(False)
                sw.setText(t("Activa") if k in activas else t("Inactiva"))
                sw.setEnabled(True); sw.setToolTip("")
            self.filas_monto[k].setVisible(not auto)
            if regimenes:
                nivel, texto = M.evaluar(hist, k, regimenes)
            else:
                nivel, texto = "sin_datos", t("Esperando la lectura del mercado…")
            txt, col = NIVELES[nivel]
            chip(rec, t(txt), col)
            porque.setText(texto)
            porque.setStyleSheet(f"font-size:13px; color:{col if nivel != 'sin_datos' else MUTED}")
            if hist and k in hist["estrategias"]:
                for r, x in celdas.items():
                    d = (hist["estrategias"][k].get("reciente", {}) if r == "Reciente"
                         else hist["estrategias"][k]["regimenes"].get(r, {}))
                    if not d.get("ops"):
                        x.setText(t("Sin operaciones")); x.setStyleSheet(f"font-size:13px; color:{MUTED}"); continue
                    pf = d.get("pf")
                    conf = d["ops"] >= M.MIN_OPS
                    x.setText(t("{pf} en {n} operaciones", pf=num(pf) if pf is not None else "—", n=d["ops"]))
                    colx = (GAIN if pf and pf >= M.PF_RECOMENDABLE else LOSS if pf and pf < 1 else TEXT) if conf else MUTED
                    x.setStyleSheet(f"font-size:13px; color:{colx}")
            for a in K.SYMBOLS:
                self.montos_w[(k, a)].setEnabled(k in activas)
        self.w_auto_montos.setVisible(False)  # en automático el capital se reparte solo
        self.w_botones_montos.setVisible(not auto)
        self.lbl_montos_tit.setText(t("Dinero de las estrategias"))
        self.lbl_montos_ayuda.setText(
            t("En modo automático el bot usa todo el capital (el del modo más lo que vaya ganando) y lo reparte en partes "
              "iguales entre las estrategias que elige en las tres monedas. Si en una moneda no conviene ninguna, su "
              "parte va a las otras. Para cambiar cuánto usa en total, cambiá el capital del modo en Configuración.")
            if auto else
            t("Elegí en cada estrategia cuántos USDT usa en BTC, ETH y SOL. Cada monto pasa a ser el capital de esa parte "
              "y desde ahí reinvierte sus ganancias. Lo que no asignes queda sin usar. Si una parte tiene una posición "
              "abierta, el monto nuevo se aplica cuando la cierre."))
        self._llenar_montos()

    # ---------- laboratorio (laboratorio.py)
    def _lab_ajustes(self):
        return PT.leer_ajustes().get("laboratorio", {}) or {}

    def _lab_estado(self):
        import archivos
        return archivos.leer_json("laboratorio_estado.json", {}, segundos=0.3) or {}

    def _lab_corriendo(self, st=None):
        st = st or self._lab_estado()
        if time.time() - getattr(self, "_lab_lanzado", 0) < 180 and st.get("inicio", 0) < getattr(self, "_lab_lanzado", 0):
            return True  # recién lanzado: todavía no escribió su estado
        return bool(st.get("corriendo")) and time.time() - st.get("latido", 0) < 300

    def _cambiar_lab(self, activo):
        aj = self._lab_ajustes(); aj["activo"] = bool(activo)
        PT.guardar_ajustes(laboratorio=aj)
        PT.log(t("Laboratorio de estrategias encendido.") if activo else t("Laboratorio de estrategias apagado."))
        if activo:
            QTimer.singleShot(2000, self._lab_tick)
        self._llenar_lab()

    def _lab_tick(self):
        """Lanza el laboratorio cada 6 horas si está activo."""
        if PRUEBA or not self._lab_ajustes().get("activo"):
            return
        st = self._lab_estado()
        if self._lab_corriendo(st):
            return
        fallo = str(st.get("mensaje", "")).startswith("error") or (st and not st.get("fin"))
        ultimo = max(st.get("fin", 0), st.get("latido", 0), getattr(self, "_lab_lanzado", 0))
        espera = 3600 if fallo else 6 * 3600  # si la última búsqueda falló, reintenta en 1 hora
        if time.time() - ultimo >= espera:
            self._lanzar_lab()

    def _lanzar_lab(self, manual=False):
        if PRUEBA:
            aviso(self, t("Modo prueba"), t("En modo prueba no corre el laboratorio.")); return
        if self._lab_corriendo():
            return
        flags = 0x08000000 if os.name == "nt" else 0  # sin ventana
        try:
            with open("laboratorio.log", "a", encoding="utf-8") as out:
                subprocess.Popen([sys.executable, os.path.abspath("laboratorio.py"), "--minutos", "20"], cwd=os.getcwd(),
                                 stdout=out, stderr=out, creationflags=flags)
            self._lab_lanzado = time.time()
            PT.log(t("Laboratorio de estrategias: búsqueda iniciada (20 minutos)."))
        except OSError as e:
            aviso(self, t("Laboratorio de estrategias"), t("No se pudo iniciar:") + f" {e}", True)
        self._llenar_lab()

    def _candidatas(self):
        out = []
        if os.path.isdir("candidatas"):
            for fn in sorted(os.listdir("candidatas")):
                if fn.startswith("LAB_") and fn.endswith(".json"):
                    try:
                        with open(os.path.join("candidatas", fn), encoding="utf-8") as f:
                            out.append(json.load(f))
                    except (OSError, ValueError):
                        pass
        return sorted(out, key=lambda d: -d.get("numero", 0))

    def _llenar_lab(self):
        aj, st = self._lab_ajustes(), self._lab_estado()
        self.sw_lab.blockSignals(True); self.sw_lab.setChecked(bool(aj.get("activo"))); self.sw_lab.blockSignals(False)
        self.sw_lab.setText(t("Activo") if aj.get("activo") else t("Apagado"))
        corriendo = self._lab_corriendo(st)
        self.btn_lab.setEnabled(not corriendo)
        if corriendo:
            txt = t("Buscando… {n} combinaciones probadas en esta corrida.", n=st.get("probadas", 0))
        elif st.get("fin"):
            txt = t("Última búsqueda: {h}. Probó {n} combinaciones ({tot} en total).",
                    h=f"{datetime.fromtimestamp(st['fin']):%d/%m %H:%M}", n=st.get("probadas", 0),
                    tot=st.get("probadas_total", 0))
            if str(st.get("mensaje", "")).startswith("error"):
                txt += " " + t("Terminó con un error:") + " " + st["mensaje"][7:150]
            elif st.get("finalistas") and not st.get("nuevas"):
                txt += " " + t("Ninguna de las mejores pasó la prueba con datos nuevos.")
        else:
            txt = t("Todavía no buscó estrategias.") if aj.get("activo") else t("Apagado. Encendelo para que busque.")
        self.lbl_lab.setText(txt)
        cands = self._candidatas()
        firma = tuple(d["id"] for d in cands) + (i18n.LANG,)
        if firma == self._cand_firma:
            return
        self._cand_firma = firma
        self._vaciar(self.box_cand)
        if not cands:
            self.box_cand.addWidget(lbl(t("No hay candidatas por ahora. Es normal: la gran mayoría de las combinaciones no "
                                          "pasa las pruebas."), rol="muted", size=12, wrap=True))
            return
        import catalogo
        import reglas
        for d in cands:
            c = QFrame(); c.setObjectName("actualizacion"); cv = QVBoxLayout(c); cv.setContentsMargins(14, 12, 14, 12)
            cv.setSpacing(6)
            top = QHBoxLayout(); top.addWidget(lbl(catalogo.nombre(d, i18n.LANG), size=14, weight=600)); ch = lbl("", rol="chip")
            chip(ch, t("Candidata"), ACCENT); top.addWidget(ch); top.addStretch()
            top.addWidget(lbl(t("Encontrada el {f}", f=d.get("creada", "")), rol="muted", size=12)); cv.addLayout(top)
            cv.addWidget(lbl(reglas.describir(d), size=13, wrap=True))
            v = d.get("validacion", {})
            en, pr = v.get("entreno", {}), v.get("prueba", {})
            mon = ", ".join(f"{a} {pct(m['resultado'], 1, True)}" for a, m in v.get("por_moneda", {}).items())
            cv.addWidget(lbl(t("Entrenamiento (2022 a 2024): ganó {pf1} veces lo que perdió, en {n1} operaciones. Prueba con "
                               "datos que no usó para crearla (2025 a hoy): {pf2} veces, en {n2} operaciones. Resultado de "
                               "la prueba por moneda (sumando cada operación): {m}.", pf1=num(en.get("pf")),
                               n1=en.get("ops"), pf2=num(pr.get("pf")), n2=pr.get("ops"), m=mon), size=12, wrap=True,
                             color=GAIN))
            hb = QHBoxLayout(); hb.setSpacing(8)
            hb.addWidget(boton(t("Agregar a mis estrategias"), "primario", lambda _=False, d=d: self._agregar_candidata(d)))
            hb.addWidget(boton(t("Descartar"), accion=lambda _=False, d=d: self._descartar_candidata(d)))
            hb.addStretch()
            hb.addWidget(boton(t("Proponer para todos"), accion=lambda _=False, d=d: self._proponer(d),
                               tip=t("Abre una propuesta en GitHub con esta estrategia para que se sume al catálogo de "
                                     "todos los usuarios.")))
            cv.addLayout(hb)
            self.box_cand.addWidget(c)

    def _agregar_candidata(self, d):
        import catalogo
        if not preguntar(self, t("Laboratorio de estrategias"), t(
                "¿Agregar {e} a tus estrategias?", e=catalogo.nombre(d, i18n.LANG)) + "\n\n" + t(
                "Aparece en la lista de estrategias como cualquier otra, apagada. Antes de activarla conviene dejarla "
                "unos días en modo simulado o demo. Para que aparezca, la app se reinicia."),
                t("Agregar y reiniciar"), t("Cancelar")):
            return
        catalogo.guardar_propia(d)
        try:
            os.remove(os.path.join("candidatas", d["id"] + ".json"))
        except OSError:
            pass
        PT.log(t("Estrategia {e} agregada desde el laboratorio.", e=d["id"]))
        self.reiniciar_app()

    def _descartar_candidata(self, d):
        os.makedirs(os.path.join("candidatas", "descartadas"), exist_ok=True)
        try:
            os.replace(os.path.join("candidatas", d["id"] + ".json"), os.path.join("candidatas", "descartadas", d["id"] + ".json"))
        except OSError:
            pass
        self._cand_firma = None
        self._llenar_lab()

    def _quitar_propia(self, k):
        import catalogo
        if k in (self.snap or {}).get("activas", []) or any(f["clave"] == k and f["lado"] for f in (self.snap or {}).get("posiciones", [])):
            aviso(self, t("Estrategias"), t("Primero desactivala y esperá a que cierre sus posiciones.")); return
        if not preguntar(self, t("Estrategias"), t("¿Quitar {e} de tus estrategias? La app se reinicia.",
                                                    e=M.nombre_estrategia(k)), t("Quitar y reiniciar"), t("Cancelar")):
            return
        catalogo.quitar_propia(k)
        self.reiniciar_app()

    def _proponer(self, d):
        """Abre en el navegador una propuesta en GitHub (la envía el usuario con su cuenta: la app no sube nada)."""
        import urllib.parse
        import catalogo
        import reglas
        limpio = {k: v for k, v in d.items() if not k.startswith("_")}
        v = d.get("validacion", {})
        cuerpo = (f"Estrategia propuesta desde la app (versión {K.VERSION}).\n\n**{catalogo.nombre(d, 'es')}**\n\n"
                  f"{reglas.describir(d)}\n\nValidación: entrenamiento {v.get('entreno')}, prueba {v.get('prueba')}, "
                  f"por moneda {v.get('por_moneda')}.\n\n```json\n{json.dumps(limpio, ensure_ascii=False, indent=1)}\n```\n")
        url = (f"https://github.com/{K.REPO}/issues/new?" +
               urllib.parse.urlencode({"title": f"Propuesta de estrategia: {catalogo.nombre(d, 'es')}", "body": cuerpo[:6000]}))
        QDesktopServices.openUrl(QUrl(url))

    # ---------- avisos (alertas.py)
    def _llenar_avisos(self):
        import alertas
        sin_leer = alertas.listar(solo_sin_leer=True)
        firma = tuple(a["id"] for a in sin_leer)
        if self._avisos_vistos is None:
            self._avisos_vistos = set(firma)  # al abrir la app no notifica lo que ya estaba
        nuevos = [a for a in sin_leer if a["id"] not in self._avisos_vistos]
        if nuevos and getattr(self, "tray", None) and PT.leer_ajustes().get("notificaciones", True):
            self.tray.showMessage(nuevos[0]["titulo"], nuevos[0]["texto"][:240], QSystemTrayIcon.Information, 8000)
        self._avisos_vistos.update(firma)
        n = len(sin_leer)
        self.nav_btns[3].setText(t("Estrategias") + (f"  ({n})" if n else ""))
        if firma == self._avisos_firma:
            return
        self._avisos_firma = firma
        self._vaciar(self.box_avisos)
        colores = {"empeora": LOSS, "recupera": GAIN, "candidata": ACCENT}
        for a in sin_leer[:8]:
            w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
            v.addWidget(lbl(f"{datetime.fromtimestamp(a['hora']):%d/%m %H:%M}  ·  {a['titulo']}", size=13, weight=600,
                            color=colores.get(a["tipo"], TEXT), wrap=True))
            v.addWidget(lbl(a["texto"], rol="muted", size=12, wrap=True))
            self.box_avisos.addWidget(w)
        self.pan_avisos.setVisible(bool(sin_leer))

    def _leer_avisos(self):
        import alertas
        alertas.marcar_leidas()
        self._avisos_firma = None
        self._llenar_avisos()

    # ---------- montos por estrategia y moneda
    def _disponible(self):
        return self.snap["saldo_cerrado"] if self.snap and self.snap["hay_estado"] else K.INITIAL_CAPITAL

    def _llenar_montos(self, forzar=False):
        if not self.snap:
            return
        if forzar or not self._montos_sucios:
            asig = self.snap["asignacion"] or PT.asignacion_por_defecto(self._disponible(), self.snap["activas"])
            self._llenando_montos = True
            for (k, a), sp in self.montos.items():
                sp.setValue(float(asig.get(f"{a}_{k}", 0.0)))
            import auto as AU
            ma = self.snap.get("auto_montos") or AU.montos_por_defecto(asig, self.snap["activas"], self._disponible())
            for a, sp in self.montos_auto.items():
                sp.setValue(float(ma.get(a, 0.0)))
            self._llenando_montos = False
            self._montos_sucios = False
        self._resumen_montos()

    def _montos_editados(self, *_):
        if not self._llenando_montos:
            self._montos_sucios = True
            self._resumen_montos()
            if not hasattr(self, "_t_montos"):
                self._t_montos = QTimer(self); self._t_montos.setSingleShot(True)
                self._t_montos.timeout.connect(lambda: self._guardar_montos(silencioso=True))
            self._t_montos.start(2000)  # se guardan solos a los 2 segundos de dejar de tocarlos

    def _suma_montos(self):
        if self.snap and self.snap.get("auto"):
            return self._disponible()
        activas = self.snap["activas"] if self.snap else []
        return sum(sp.value() for (k, _), sp in self.montos.items() if k in activas)

    def _resumen_montos(self):
        disp, asig = self._disponible(), self._suma_montos()
        resto = disp - asig
        if self.snap and self.snap.get("auto"):
            partes = sum(len(v) for v in (self.snap.get("activas_moneda") or {}).values())
            txt = (t("Usa {d}, repartido en {n} partes de {x} cada una.", d=usd(disp), n=partes, x=usd(disp / partes))
                   if partes else t("Ninguna estrategia conviene ahora: los {d} quedan sin usar hasta que cambie el "
                                    "mercado.", d=usd(disp)))
            self.lbl_montos.setText(txt); self.lbl_montos.setStyleSheet(f"font-size:13px; color:{TEXT}")
            bajos = []
            if partes:
                for a, sel in (self.snap.get("activas_moneda") or {}).items():
                    for k in sel:
                        mn = self._monto_minimo(k, a)
                        if mn and disp / partes < mn:
                            bajos.append((k, a, disp / partes, mn))
            self._texto_minimos(bajos)
            return
        else:
            txt = t("Disponible: {d} (capital del modo más resultado cerrado). Asignado a estrategias activas: {a}. "
                    "Sin asignar: {r}.", d=usd(disp), a=usd(asig), r=usd(resto))
        if resto < -0.005:
            txt += " " + t("Te pasaste por {x}: bajá algún monto antes de guardar.", x=usd(-resto))
            col = LOSS
        elif self._montos_sucios:
            txt += " " + t("Guardando…")
            col = AMBER
        else:
            col = TEXT
        self.lbl_montos.setText(txt); self.lbl_montos.setStyleSheet(f"font-size:13px; color:{col}")
        self.btn_guardar_montos.setEnabled(self._montos_sucios and resto >= -0.005)
        self.btn_deshacer_montos.setEnabled(self._montos_sucios)
        self._texto_minimos()

    def _texto_minimos(self, partes_auto=None):
        if K.MODO == "simulado":
            self.lbl_minimos.setText(t("En modo simulado no hay tamaño mínimo por orden. En Binance sí: con montos muy "
                                       "chicos el bot saltea las señales que no llegan al mínimo."))
            self.lbl_minimos.setStyleSheet(f"font-size:12px; color:{MUTED}")
            return
        mins = self.mkt.minimos
        if not mins:
            self.lbl_minimos.setText(t("Leyendo de Binance el tamaño mínimo por orden de cada moneda…"))
            return
        txt = t("Binance pide un tamaño mínimo por orden: {m}. El tamaño de cada orden es el monto de la estrategia por el "
                "riesgo ({r}) dividido la distancia al stop, así que el monto mínimo cambia con la volatilidad. Pasá el "
                "mouse por cada monto para ver el mínimo de hoy.", m=", ".join(f"{a} {usd(c, 0)}" for a, c in mins.items()),
                r=pct(K.RISK_PER_TRADE * 100, 0))
        bajos = self._marcar_minimos() if partes_auto is None else partes_auto
        if bajos:
            txt += " " + t("Hoy no llegan al mínimo, y el bot va a saltear sus señales: {l}.", l="; ".join(
                f"{a} {M.nombre_estrategia(k)} ({usd(v, 0)}, {t('mínimo')} {usd(mn, 0)})" for k, a, v, mn in bajos))
            self.lbl_minimos.setStyleSheet(f"font-size:12px; color:{LOSS}")
        else:
            self.lbl_minimos.setStyleSheet(f"font-size:12px; color:{MUTED}")
        self.lbl_minimos.setText(txt)

    def _monto_minimo(self, k, a):
        """Monto aproximado que necesita una estrategia en una moneda para que su orden llegue al mínimo de Binance.
        El tamaño de cada orden es monto × riesgo ÷ distancia al stop, y la distancia depende de la volatilidad actual."""
        if K.MODO == "simulado":
            return None
        from engine import STRATS
        mn, an = self.mkt.minimos.get(a), self.mkt.analisis.get(a)
        if not mn or not an or not an.get("atr_pct") or k not in STRATS:
            return None
        return mn * STRATS[k]["stop_atr"] * an["atr_pct"] / K.RISK_PER_TRADE

    def _marcar_minimos(self):
        """Marca en rojo los montos que hoy no llegan al mínimo de Binance. Devuelve la lista de los que no llegan."""
        bajos = []
        activas = (self.snap or {}).get("activas", [])
        for (k, a), sp in self.montos.items():
            mn = self._monto_minimo(k, a) if k in activas else None
            if mn is not None and 0 < sp.value() < mn:
                sp.setStyleSheet(f"border: 1px solid {LOSS}; border-radius: 8px; background: {PANEL2};")
                sp.setToolTip(t("Con la volatilidad de hoy, {a} necesita al menos unos {m} para que la orden llegue al "
                                "mínimo de Binance.", a=a, m=usd(mn, 0)))
                bajos.append((k, a, sp.value(), mn))
            else:
                sp.setStyleSheet("")
                sp.setToolTip(t("Mínimo aproximado hoy: {m}", m=usd(mn, 0)) if mn else "")
        return bajos

    def _montos_actuales(self):
        return {f"{a}_{k}": round(sp.value(), 2) for (k, a), sp in self.montos.items()}

    def _guardar_montos(self, silencioso=False):
        if not self._montos_sucios:
            return
        if PRUEBA:
            if not silencioso:
                aviso(self, t("Modo prueba"), t("En modo prueba no se cambian los montos del bot."))
            return
        resto = self._disponible() - self._suma_montos()
        if resto < -0.005:
            if not silencioso:
                aviso(self, t("Montos"), t("La suma de los montos supera lo disponible por {x}.", x=usd(-resto)), True)
            return
        if self.snap.get("auto"):
            PT.guardar_auto(montos={a: sp.value() for a, sp in self.montos_auto.items()})
            PT.log(t("Dinero por moneda del modo automático cambiado desde la aplicación."))
        else:
            PT.guardar_asignacion(self._montos_actuales())
            PT.log(t("Montos por estrategia y moneda cambiados desde la aplicación."))
        self._montos_sucios = False
        self.bot.revisar_ahora()  # los aplica ahora mismo (no opera si no hay velas nuevas)
        QTimer.singleShot(2500, self.refrescar)
        self._resumen_montos()

    def _repartir_montos(self):
        if self.snap and self.snap.get("auto"):
            self._llenando_montos = True
            for sp in self.montos_auto.values():
                sp.setValue(int(self._disponible() / len(K.SYMBOLS) * 100) / 100)
            self._llenando_montos = False
            self._montos_sucios = True
            self._resumen_montos(); return
        activas = self.snap["activas"] if self.snap else []
        por = self._disponible() / (len(K.SYMBOLS) * max(1, len(activas)))
        self._llenando_montos = True
        for (k, a), sp in self.montos.items():
            if k in activas:
                sp.setValue(int(por * 100) / 100)
        self._llenando_montos = False
        self._montos_sucios = True
        self._resumen_montos()

    def _cambiar_auto(self, activar):
        if PRUEBA:
            aviso(self, t("Modo prueba"), t("En modo prueba no se cambia cómo se eligen las estrategias."))
            self._llenar_estrategias(); return
        if activar:
            if not self.mkt.historial:
                aviso(self, t("Estrategias"), t("Para el modo automático hace falta el historial de estrategias. Esperá a que "
                                                "termine de calcularse (lo ves arriba de la lista de estrategias)."))
                self._llenar_estrategias(); return
            msg = (t("¿Pasar al modo automático?") + "\n\n" +
                   t("El bot va a elegir en cada revisión qué estrategias usar en cada moneda según el tipo de mercado, y "
                     "va a repartir todo el capital ({d}, más lo que vaya ganando) en partes iguales entre las que elija. "
                     "Las posiciones abiertas se siguen manejando hasta cerrarse.", d=usd(self._disponible())))
            if not preguntar(self, t("Estrategias"), msg, t("Pasar a automático"), t("Cancelar")):
                self._llenar_estrategias(); return
            PT.guardar_auto(activo=True)
            PT.log(t("Modo automático de estrategias encendido desde la aplicación."))
        else:
            if not preguntar(self, t("Estrategias"), t("¿Volver al modo manual?") + "\n\n" + t(
                    "El bot vuelve a usar las estrategias que actives a mano, con los montos por estrategia y moneda que "
                    "tenías. Las posiciones abiertas se siguen manejando hasta cerrarse."), t("Volver a manual"),
                    t("Cancelar")):
                self._llenar_estrategias(); return
            PT.guardar_auto(activo=False)
            PT.log(t("Modo automático de estrategias apagado desde la aplicación."))
        self._montos_sucios = False
        self.bot.revisar_ahora()
        QTimer.singleShot(2500, self.refrescar)

    def _cambiar_estrategia(self, k, activar):
        if PRUEBA:
            aviso(self, t("Modo prueba"), t("En modo prueba no se cambian las estrategias del bot."))
            self._llenar_estrategias(); return
        self._guardar_montos(silencioso=True)  # no perder montos escritos y todavía sin guardar
        activas = list(self.snap["activas"])
        nombre = M.nombre_estrategia(k)
        if not activar and activas == [k]:
            aviso(self, t("Estrategias"), t("Tiene que quedar al menos una estrategia activa."))
            self._llenar_estrategias(); return
        asig = dict(PT.asignacion_actual() or self.snap["asignacion"] or {})
        nuevos = None
        if activar:
            ya = sum(asig.get(f"{a}_{k}", 0.0) for a in K.SYMBOLS)
            resto = self._disponible() - sum(v for kk, v in asig.items() if kk.split("_", 1)[1] in activas)
            if ya > 0:
                detalle = t("Vuelve a usar los montos que tenía: {m}.",
                            m=", ".join(f"{a} {usd(asig.get(f'{a}_{k}', 0.0))}" for a in K.SYMBOLS))
            elif resto >= 1:
                por = int(resto / len(K.SYMBOLS) * 100) / 100
                nuevos = {f"{a}_{k}": por for a in K.SYMBOLS}
                detalle = t("Se le asignan {x} por moneda del capital sin asignar. Podés cambiarlo abajo, en Monto por "
                            "moneda.", x=usd(por))
            else:  # no hay capital sin asignar: hay que sacarle a otras
                op = elegir(self, t("Estrategias"), t("¿Activar {e}?", e=nombre) + "\n\n" + t(
                    "No tenés capital sin asignar: todo está repartido entre las estrategias que ya están activas. Para que "
                    "{e} opere hay que darle una parte.", e=nombre) + "\n\n" + t(
                    "• Repartir como recomienda el bot: vuelve a repartir todo el capital entre las estrategias activas, "
                    "con más dinero para las que mejor funcionan en el mercado de hoy (es el mismo botón que está en "
                    "Configuración → Capital de cada modo). Te muestra el reparto antes de guardarlo.") + "\n" + t(
                    "• Asignar a mano: la activa con 0 USDT; después bajá el monto de otras estrategias y ponele monto a "
                    "esta, más abajo en su tarjeta."), [t("Repartir como recomienda el bot"), t("Asignar a mano"),
                                                        t("Cancelar")])
                if op not in (0, 1):
                    self._llenar_estrategias(); return
                activas_n = sorted(set(activas + [k]), key=list(PT.NOMBRES).index)
                PT.guardar_activas(activas_n)
                self._montos_sucios = False
                if op == 0:
                    self.snap["activas"] = activas_n
                    self._guardar_y_repartir(activas=activas_n)
                else:
                    self.bot.revisar_ahora()
                    sp = self.montos.get((k, list(K.SYMBOLS)[0]))
                    if sp:
                        QTimer.singleShot(600, lambda: (sp.setFocus(), sp.selectAll()))
                QTimer.singleShot(2500, self.refrescar)
                return
            msg = t("¿Activar {e}?", e=nombre) + "\n\n" + t("Va a operar en BTC, ETH y SOL.") + " " + detalle
        else:
            msg = t("¿Desactivar {e}?", e=nombre) + "\n\n" + t(
                "No va a abrir posiciones nuevas. Si tiene alguna abierta, la sigue manejando hasta cerrarla. Su dinero "
                "vuelve al capital sin asignar; los montos quedan guardados por si la volvés a activar.")
        if not preguntar(self, t("Estrategias"), msg, t("Activar") if activar else t("Desactivar"), t("Cancelar")):
            self._llenar_estrategias(); return
        if nuevos:
            asig.update(nuevos); PT.guardar_asignacion(asig)
        activas = activas + [k] if activar else [x for x in activas if x != k]
        orden = list(PT.NOMBRES)
        PT.guardar_activas(sorted(set(activas), key=orden.index))
        self._montos_sucios = False
        self.bot.revisar_ahora()
        QTimer.singleShot(2500, self.refrescar)

    def _ver_versiones(self):
        m = QMessageBox(self); m.setWindowTitle(t("Versiones")); m.setTextFormat(Qt.RichText)
        m.setText(self._html_versiones()); m.addButton(t("Cerrar"), QMessageBox.AcceptRole); m.exec()

    def _html_versiones(self):
        txt = ""
        for v, fecha, cambios in K.HISTORIAL_VERSIONES:
            txt += f"<p><b>{t('Versión {v}', v=v)}</b> <span style='color:{MUTED}'>({fecha})</span></p><ul>"
            txt += "".join(f"<li>{t(c)}</li>" for c in cambios) + "</ul>"
        return txt

    # ---------- configuración
    def _seccion(self, iv, titulo, sub=None):
        p = panel(); pv = QVBoxLayout(p); pv.setContentsMargins(20, 16, 20, 18); pv.setSpacing(10)
        pv.addWidget(lbl(titulo, rol="titulo"))
        if sub:
            pv.addWidget(lbl(sub, rol="muted", size=12, wrap=True))
        iv.addWidget(p)
        return pv

    def _pag_configuracion(self):
        w, v = self._pagina(t("Configuración"), t(
            "Cómo poner el bot a funcionar, el modo de operación y las claves de Binance, el capital, el riesgo, tus "
            "preferencias y las actualizaciones."))
        inner = QWidget(); inner.setObjectName("pagina"); inner.setMaximumWidth(1040)
        iv = QVBoxLayout(inner); iv.setContentsMargins(0, 0, 10, 0); iv.setSpacing(14)

        # guía
        pv = self._seccion(iv, t("Primeros pasos"), t("Qué hacer, en orden, para que el bot opere en Binance."))
        g = QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(12); g.setColumnStretch(1, 1)
        for i, (tit, txt, links) in enumerate(GUIA):
            n = lbl(str(i + 1), rol="num"); n.setFixedSize(24, 24); n.setAlignment(Qt.AlignCenter)
            g.addWidget(n, i, 0, Qt.AlignTop)
            col = QVBoxLayout(); col.setSpacing(3)
            col.addWidget(lbl(t(tit), size=14, weight=600)); col.addWidget(lbl(t(txt), rol="muted", size=13, wrap=True))
            for texto, url in links:
                if i18n.LANG == "en":
                    url = url.replace("/es/", "/en/")
                ln = lbl(f'<a href="{url}" style="color:{ACCENT}; text-decoration:none">{t(texto)} ↗</a>', size=13)
                ln.setTextFormat(Qt.RichText); ln.setOpenExternalLinks(True); ln.setToolTip(url)
                ln.setTextInteractionFlags(Qt.TextBrowserInteraction)
                col.addWidget(ln)
            g.addLayout(col, i, 1)
        pv.addLayout(g)

        # modo
        pv = self._seccion(iv, t("Modo de operación"), t(
            "Cada modo tiene su propio capital, operaciones y registro. Al cambiar de modo, las posiciones del modo anterior "
            "quedan como están."))
        fila = QHBoxLayout(); fila.setSpacing(12); self.btn_modos = {}
        textos = {"simulado": "Órdenes simuladas, sin claves", "demo": "Cuenta demo, dinero de prueba",
                  "real": "Tu cuenta, tu dinero"}
        for m in ("simulado", "demo", "real"):
            b = QPushButton(f"{t(K.NOMBRE_MODO[m])}\n{t(textos[m])}"); b.setProperty("rol", "modo"); b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor); b.setMinimumHeight(70)
            b.clicked.connect(lambda _=False, m=m: self._cambiar_modo(m))
            fila.addWidget(b, 1); self.btn_modos[m] = b
        pv.addLayout(fila)
        self.lbl_modo_info = lbl("", size=13, wrap=True); pv.addWidget(self.lbl_modo_info)

        # capital
        pv = self._seccion(iv, t("Capital de cada modo"), t(
            "Cuánto dinero de la cuenta usa el bot en cada modo. Podés cambiarlo cuando quieras: si lo subís, la diferencia "
            "queda sin asignar hasta que la repartas en Estrategias; si lo bajás, solo se puede sacar lo que no está "
            "asignado (bajá antes los montos)."))
        g = QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(8)
        self.sp_capital = {}
        caps = PT.leer_ajustes().get("capital", {})
        for i, m in enumerate(("simulado", "demo", "real")):
            g.addWidget(lbl(t(K.NOMBRE_MODO[m]), size=13), i, 0)
            sp = QDoubleSpinBox(); sp.setRange(10, 1_000_000); sp.setDecimals(2); sp.setSingleStep(50)
            sp.setSuffix(NB + "USDT"); sp.setValue(float(caps.get(m, 100))); sp.setMinimumWidth(170)
            g.addWidget(con_pasos(sp), i, 1); self.sp_capital[m] = sp
        g.setColumnStretch(2, 1)
        pv.addLayout(g)
        h = QHBoxLayout(); h.setSpacing(8)
        h.addWidget(boton(t("Guardar capital"), "primario", self._guardar_capital))
        h.addWidget(boton(t("Guardar y repartir como recomienda el bot"), accion=self._guardar_y_repartir, tip=t(
            "Guarda el capital y reparte todo el capital del modo actual entre las estrategias activas en cada moneda, "
            "con más dinero para las que mejor funcionaron en el tipo de mercado de hoy y respetando el mínimo de Binance.")))
        h.addStretch()
        pv.addLayout(h)
        self.lbl_cap_res = lbl("", size=13, wrap=True); pv.addWidget(self.lbl_cap_res)
        self.lbl_cap_aviso = lbl("", size=13, wrap=True, color=LOSS); self.lbl_cap_aviso.setVisible(False)
        pv.addWidget(self.lbl_cap_aviso)

        # claves
        self.ui_claves = {}
        for m, titulo in (("demo", t("Cuenta demo de Binance")), ("real", t("Cuenta real de Binance"))):
            ayuda = (t("Claves creadas en Trading de prueba de Binance, en Gestión de API.") if m == "demo" else
                     t("Creá una clave en binance.com, en Gestión de API, con permiso de futuros y SIN permiso de retiros. "
                       "Si podés, restringila a la IP de tu conexión."))
            pv = self._seccion(iv, titulo, ayuda)
            estado = lbl("", size=12)
            pv.insertWidget(1, estado)
            g = QGridLayout(); g.setHorizontalSpacing(12); g.setVerticalSpacing(8); g.setColumnStretch(1, 1)
            key, sec = QLineEdit(), QLineEdit()
            key.setPlaceholderText(t("Pegá acá la clave de API")); sec.setPlaceholderText(t("Solo si Binance te dio una clave secreta"))
            key.setEchoMode(QLineEdit.Password); sec.setEchoMode(QLineEdit.Password)
            g.addWidget(lbl(t("Clave de API"), rol="muted", size=12), 0, 0); g.addWidget(key, 0, 1)
            g.addWidget(lbl(t("Clave secreta"), rol="muted", size=12), 1, 0); g.addWidget(sec, 1, 1)
            pv.addLayout(g)
            h = QHBoxLayout(); h.setSpacing(8)
            botones = {}
            acciones = [("ed", t("Generar clave Ed25519"), "accion", lambda _=False, m=m: self._generar_ed25519(m)),
                        ("guardar", t("Guardar claves"), "primario", lambda _=False, m=m: self._guardar_claves(m)),
                        ("probar", t("Probar conexión"), "accion", lambda _=False, m=m: self._probar(m, "conexion"))]
            if m == "demo":
                acciones.append(("ordenes", t("Probar órdenes"), "accion", lambda _=False, m=m: self._probar(m, "ordenes")))
            acciones.append(("borrar", t("Borrar claves"), "peligro", lambda _=False, m=m: self._borrar_claves(m)))
            for kk, n, rol, f in acciones:
                b = boton(n, rol, f); h.addWidget(b); botones[kk] = b
            h.addStretch(); pv.addLayout(h)
            pub = QPlainTextEdit(); pub.setReadOnly(True); pub.setMaximumHeight(70); pub.setVisible(False)
            pv.addWidget(pub)
            res = lbl("", size=13, wrap=True); pv.addWidget(res)
            self.ui_claves[m] = dict(estado=estado, key=key, sec=sec, res=res, botones=botones, pub=pub)

        # preferencias
        pv = self._seccion(iv, t("Preferencias"))
        g = QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(10); g.setColumnStretch(2, 1)
        self.cmb_idioma = QComboBox()
        for code, n in (("es", "Español"), ("en", "English")):
            self.cmb_idioma.addItem(n, code)
        self.cmb_idioma.setCurrentIndex(0 if i18n.LANG == "es" else 1)
        self.cmb_idioma.currentIndexChanged.connect(lambda _: self._cambiar_pref("idioma", self.cmb_idioma.currentData()))
        g.addWidget(lbl(t("Idioma"), size=13), 0, 0); g.addWidget(self.cmb_idioma, 0, 1)
        self.cmb_tema = QComboBox()
        for code, n in (("oscuro", t("Oscuro (negro y naranja)")), ("claro", t("Claro (blanco y naranja)"))):
            self.cmb_tema.addItem(n, code)
        self.cmb_tema.setCurrentIndex(0 if TEMA == "oscuro" else 1)
        self.cmb_tema.currentIndexChanged.connect(lambda _: self._cambiar_pref("tema", self.cmb_tema.currentData()))
        g.addWidget(lbl(t("Tema"), size=13), 1, 0); g.addWidget(self.cmb_tema, 1, 1)
        pv.addLayout(g)
        self.chk_notif = QCheckBox(t("Avisarme con una notificación cuando el bot abre o cierra una posición"))
        self.chk_notif.setChecked(PT.leer_ajustes().get("notificaciones", True))
        self.chk_notif.toggled.connect(lambda v: PT.guardar_ajustes(notificaciones=bool(v)))
        pv.addWidget(self.chk_notif)
        self.chk_inicio = QCheckBox(t("Abrir el bot automáticamente al iniciar Windows (queda en el ícono junto a la hora)"))
        est = inicio_windows()
        self.chk_inicio.setChecked(bool(est)); self.chk_inicio.setEnabled(est is not None)
        self.chk_inicio.toggled.connect(self._cambiar_inicio)
        pv.addWidget(self.chk_inicio)
        self.lbl_pref = lbl("", size=13, wrap=True); pv.addWidget(self.lbl_pref)

        # riesgo
        pv = self._seccion(iv, t("Riesgo"), t(
            "Valores probados: 3 % por operación, límite de pérdida de 25 % y 180 segundos de espera de la orden límite. Más "
            "riesgo puede ganar más pero también perder mucho más rápido."))
        g = QGridLayout(); g.setHorizontalSpacing(14); g.setVerticalSpacing(8); g.setColumnStretch(2, 1)
        self.sp_riesgo = QDoubleSpinBox(); self.sp_riesgo.setRange(0.5, 5); self.sp_riesgo.setSingleStep(0.5)
        self.sp_riesgo.setDecimals(1); self.sp_riesgo.setSuffix(NB + "%"); self.sp_riesgo.setValue(K.RISK_PER_TRADE * 100)
        self.sp_limite = QDoubleSpinBox(); self.sp_limite.setRange(10, 50); self.sp_limite.setSingleStep(5)
        self.sp_limite.setDecimals(0); self.sp_limite.setSuffix(NB + "%"); self.sp_limite.setValue(K.LIMITE_PERDIDA * 100)
        self.sp_espera = QDoubleSpinBox(); self.sp_espera.setRange(30, 600); self.sp_espera.setSingleStep(30)
        self.sp_espera.setDecimals(0); self.sp_espera.setSuffix(NB + "s"); self.sp_espera.setValue(K.ESPERA_ORDEN_LIMITE)
        filas = [(t("Riesgo por operación"), self.sp_riesgo, t("Lo que se pierde si salta el stop, sobre el capital de la parte.")),
                 (t("Límite de pérdida"), self.sp_limite, t("Si el saldo cae este porcentaje, el bot deja de abrir operaciones.")),
                 (t("Espera de la orden límite"), self.sp_espera, t("Después de este tiempo, la orden se completa a mercado."))]
        for i, (n, sp, ayuda) in enumerate(filas):
            sp.setMinimumWidth(130)
            g.addWidget(lbl(n, size=13), i, 0); g.addWidget(con_pasos(sp), i, 1)
            g.addWidget(lbl(ayuda, rol="muted", size=12, wrap=True), i, 2)
        pv.addLayout(g)
        h = QHBoxLayout()
        h.addWidget(boton(t("Guardar riesgo"), "primario", self._guardar_riesgo))
        h.addWidget(boton(t("Volver a los valores probados"), accion=self._riesgo_defecto)); h.addStretch()
        pv.addLayout(h)
        self.lbl_riesgo_res = lbl("", size=13, wrap=True); pv.addWidget(self.lbl_riesgo_res)

        # seguridad
        pv = self._seccion(iv, t("Seguridad"))
        self.lbl_seg_txt = lbl("", size=13, wrap=True); pv.addWidget(self.lbl_seg_txt)
        h = QHBoxLayout(); h.setSpacing(8)
        self.btn_cerrar_todo = boton(t("Cerrar todas las posiciones del bot"), "peligro", self._cerrar_todo)
        self.btn_reanudar = boton(t("Reanudar después del límite de pérdida"), accion=self._reanudar)
        h.addWidget(self.btn_cerrar_todo); h.addWidget(self.btn_reanudar); h.addStretch(); pv.addLayout(h)
        self.lbl_seg = lbl("", rol="muted", size=12, wrap=True); pv.addWidget(self.lbl_seg)

        # acerca de
        pv = self._seccion(iv, t("Actualizaciones"), t(
            "La app busca versiones nuevas al iniciar y cada 1 hora. Si hay una, aparece un aviso abajo a la izquierda "
            "para instalarla. Instalar no toca tus operaciones, ajustes ni claves."))
        self.lbl_act = lbl("", size=13, wrap=True); pv.addWidget(self.lbl_act)
        h = QHBoxLayout(); h.setSpacing(8)
        self.btn_buscar_act = boton(t("Buscar actualizaciones"), accion=lambda: self._buscar_actualizacion(manual=True))
        self.btn_instalar_act = boton(t("Instalar actualización"), "primario", self._instalar_actualizacion)
        self.btn_instalar_act.setVisible(False)
        h.addWidget(self.btn_buscar_act); h.addWidget(self.btn_instalar_act); h.addStretch(); pv.addLayout(h)
        self.chk_auto_act = QCheckBox(t("Buscar actualizaciones automáticamente"))
        self.chk_auto_act.setChecked(PT.leer_ajustes().get("buscar_actualizaciones", True))
        self.chk_auto_act.toggled.connect(lambda v: PT.guardar_ajustes(buscar_actualizaciones=bool(v)))
        pv.addWidget(self.chk_auto_act)
        self.chk_inst_auto = QCheckBox(t("Instalar las actualizaciones automáticamente (sin preguntar)"))
        self.chk_inst_auto.setChecked(PT.leer_ajustes().get("instalar_actualizaciones_auto", False))
        self.chk_inst_auto.toggled.connect(lambda v: PT.guardar_ajustes(instalar_actualizaciones_auto=bool(v)))
        pv.addWidget(self.chk_inst_auto)

        pv = self._seccion(iv, t("Acerca de"))
        pv.addWidget(lbl(t("Bot de trading, versión {v}.", v=K.VERSION), size=13, wrap=True))
        hv = lbl(self._html_versiones(), size=13, wrap=True); hv.setTextFormat(Qt.RichText); pv.addWidget(hv)
        h = QHBoxLayout(); h.addWidget(boton(t("Abrir carpeta del bot"), accion=lambda: self._abrir(".")))
        h.addWidget(boton(t("Reiniciar la aplicación"), accion=self.reiniciar_app)); h.addStretch(); pv.addLayout(h)

        iv.addStretch()
        v.addWidget(scroll(inner), 1)
        self.t_trabajo = QTimer(self); self.t_trabajo.timeout.connect(self._ver_trabajo); self.t_trabajo.start(700)
        self._act_info, self._act_res, self._act_ocupado, self._act_prog = None, None, False, None
        self.lbl_act.setText(t("Versión instalada: {v}.", v=K.VERSION))
        self.t_act = QTimer(self); self.t_act.timeout.connect(self._buscar_auto); self.t_act.start(3600 * 1000)
        QTimer.singleShot(15000, self._buscar_auto)
        self.t_lab = QTimer(self); self.t_lab.timeout.connect(self._lab_tick); self.t_lab.start(5 * 60 * 1000)
        QTimer.singleShot(60000, self._lab_tick)
        return w

    # ---------- actualizaciones
    def _buscar_auto(self):
        if PT.leer_ajustes().get("buscar_actualizaciones", True):
            self._buscar_actualizacion(manual=False)

    def _buscar_actualizacion(self, manual=False):
        if self._act_ocupado:
            return
        self._act_ocupado, self._act_manual = True, manual
        self.btn_buscar_act.setEnabled(False)
        if manual:
            self.lbl_act.setText(t("Buscando actualizaciones…")); self.lbl_act.setStyleSheet(f"font-size:13px; color:{MUTED}")

        def tarea():
            try:
                self._act_res = ("busqueda", AC.buscar())
            except Exception as e:
                self._act_res = ("error_busqueda", str(e) if str(e) == "repo-no-configurado" else f"{type(e).__name__}: {e}")
        threading.Thread(target=tarea, daemon=True).start()

    def _instalar_sola(self):
        """Instalación automática: espera a que el bot no esté en medio de una revisión."""
        if PT.STATUS.get("estado") == "revisando" or self._act_ocupado:
            QTimer.singleShot(60000, self._instalar_sola); return
        PT.log(t("Instalando automáticamente la versión {v}.", v=self._act_info["version"]))
        self._instalar_actualizacion(confirmar=False)

    def _instalar_actualizacion(self, confirmar=True):
        info = self._act_info
        if not info or self._act_ocupado:
            return
        if PRUEBA:
            aviso(self, t("Modo prueba"), t("En modo prueba no se instalan actualizaciones.")); return
        # de las notas de la publicación quedan solo los cambios (sin el formato de GitHub)
        notas = "\n".join("• " + l.strip()[2:] for l in (info.get("notas") or "").splitlines() if l.strip().startswith("- "))
        msg = t("¿Instalar la versión {v}?", v=info["version"]) + "\n\n" + (notas[:900] + "\n\n" if notas else "") + t(
            "La app se reinicia sola al terminar (tarda menos de un minuto). Tus operaciones, ajustes y claves no se tocan, "
            "y se guarda una copia de la versión actual por si hay que volver atrás.")
        if confirmar and not preguntar(self, t("Actualización"), msg, t("Instalar"), t("Más tarde")):
            return
        self._act_ocupado = True
        for b in (self.btn_act_lat, self.btn_instalar_act, self.btn_buscar_act):
            b.setEnabled(False)
        etapas = {"descargando": t("Descargando"), "respaldando": t("Guardando una copia"), "copiando": t("Instalando"),
                  "dependencias": t("Instalando componentes"), "listo": t("Listo, reiniciando")}

        def prog(f, x):
            self._act_prog = (f, etapas.get(x, x))

        def tarea():
            try:
                AC.instalar(info, prog)
                self._act_res = ("instalada", info["version"])
            except Exception as e:
                self._act_res = ("error_instalar", f"{type(e).__name__}: {e}")
        threading.Thread(target=tarea, daemon=True).start()

    def _pintar_actualizacion(self):
        prog, self._act_prog = self._act_prog, None
        if prog:
            txt = t("{e}… {p}", e=prog[1], p=pct(prog[0] * 100, 0))
            self.lbl_act.setText(txt); self.lbl_act_lat_sub.setText(txt)
        res, self._act_res = self._act_res, None
        if not res:
            return
        tipo, dato = res
        self._act_ocupado = False
        self.btn_buscar_act.setEnabled(True)
        if tipo == "busqueda":
            self._act_info = dato
            if dato:
                self.lbl_act.setText(t("Hay una versión nueva: {v} (tenés la {a}).", v=dato["version"], a=K.VERSION))
                self.lbl_act.setStyleSheet(f"font-size:13px; color:{ACCENT}; font-weight:600")
                self.lbl_act_lat.setText(t("Actualización disponible"))
                self.lbl_act_lat_sub.setText(t("Versión {v}", v=dato["version"]))
                self.box_act.setVisible(True); self.btn_act_lat.setEnabled(True)
                self.btn_instalar_act.setVisible(True); self.btn_instalar_act.setEnabled(True)
                if not self._act_manual and PT.leer_ajustes().get("instalar_actualizaciones_auto", False) and not PRUEBA:
                    QTimer.singleShot(5000, self._instalar_sola)
                elif not self._act_manual and getattr(self, "tray", None):
                    self.tray.showMessage(t("Actualización disponible"), t("Versión {v}. Abrí la app para instalarla.",
                                                                           v=dato["version"]), QSystemTrayIcon.Information, 6000)
            else:
                self.lbl_act.setText(t("Tenés la última versión ({v}). Última búsqueda: {h}.", v=K.VERSION,
                                       h=f"{datetime.now():%H:%M}"))
                self.lbl_act.setStyleSheet(f"font-size:13px; color:{GAIN}")
                self.box_act.setVisible(False); self.btn_instalar_act.setVisible(False)
        elif tipo == "error_busqueda":
            if dato == "repo-no-configurado":
                txt = t("Todavía no hay un repositorio de actualizaciones configurado.")
            elif "404" in dato:
                txt = t("Todavía no hay versiones publicadas. Tenés la {v}.", v=K.VERSION)
            else:
                txt = t("No se pudo buscar actualizaciones (sin conexión o GitHub no responde). Se vuelve a intentar más tarde.")
            self.lbl_act.setText(txt); self.lbl_act.setStyleSheet(f"font-size:13px; color:{AMBER if self._act_manual else MUTED}")
        elif tipo == "instalada":
            self.lbl_act.setText(t("Versión {v} instalada. Reiniciando…", v=dato))
            self.lbl_act_lat_sub.setText(t("Reiniciando…"))
            PT.log(t("Actualización a la versión {v} instalada desde la aplicación.", v=dato))
            QTimer.singleShot(800, self.reiniciar_app)
        elif tipo == "error_instalar":
            self.lbl_act.setText(t("No se pudo instalar la actualización:") + " " + dato[:300] + " " +
                                 t("La versión actual sigue funcionando."))
            self.lbl_act.setStyleSheet(f"font-size:13px; color:{LOSS}")
            self.lbl_act_lat_sub.setText(t("Falló la instalación. Mirá Configuración."))
            for b in (self.btn_act_lat, self.btn_instalar_act):
                b.setEnabled(True)

    def _pintar_modo(self):
        m = K.MODO
        col = {"simulado": MUTED, "demo": AMBER, "real": LOSS}[m]
        extra = {"simulado": t("sin dinero real"), "demo": t("dinero de prueba"), "real": t("OPERA CON TU DINERO")}[m]
        self.lbl_modo.setText(f"{t(K.NOMBRE_MODO[m])}, {extra}")
        self.lbl_modo.setStyleSheet(f"font-size:12px; color:{col}; font-weight:{700 if m == 'real' else 400}")
        self.setWindowTitle(t("Bot de trading {v} · {m}", v=K.VERSION, m=t(K.NOMBRE_MODO[m])))
        for k, b in self.btn_modos.items():
            b.setChecked(k == m)
        info = {"simulado": t("El bot está en modo simulado: no manda órdenes a Binance."),
                "demo": t("El bot opera en la cuenta demo de Binance. Las órdenes son reales pero con dinero de prueba."),
                "real": t("ATENCIÓN: el bot opera con tu dinero en Binance Futuros.")}[m]
        self.lbl_modo_info.setText(info + " " + t("Capital del bot en este modo: {c}.", c=usd(K.INITIAL_CAPITAL)))
        self.lbl_modo_info.setStyleSheet(f"font-size:13px; color:{col if m != 'simulado' else TEXT}")
        en_vivo = m in ("demo", "real")
        self.btn_cerrar_todo.setEnabled(en_vivo); self.btn_reanudar.setEnabled(en_vivo)
        self.lbl_seg_txt.setText(t(
            "Si el saldo del bot cae un {p} desde su capital, deja de abrir operaciones nuevas (las abiertas mantienen su "
            "stop) hasta que lo reanudes. En los modos con Binance, cada posición tiene su stop puesto en Binance, que "
            "funciona aunque la PC esté apagada.", p=pct(K.LIMITE_PERDIDA * 100, 0)))
        for mm, u in self.ui_claves.items():
            ck = CL.cargar(mm)
            u["estado"].setText(t("Claves guardadas ({k})", k=CL.enmascarar(ck[0])) if ck else t("Sin claves guardadas"))
            u["estado"].setStyleSheet(f"font-size:12px; color:{GAIN if ck else MUTED}")

    def _guardar_capital(self):
        if PRUEBA:
            aviso(self, t("Modo prueba"), t("En modo prueba no se cambia el capital.")); return
        caps = PT.leer_ajustes().get("capital", {})
        snap = self.snap or {}
        efectivo = snap.get("base", K.INITIAL_CAPITAL) if snap.get("hay_estado") else K.INITIAL_CAPITAL
        nuevo = round(float(self.sp_capital[K.MODO].value()), 2)
        # lo que van a usar las estrategias activas según los montos guardados (aunque el bot todavía no los aplicó)
        activas = snap.get("activas") or []
        comprometido = sum(v for k_, v in (PT.asignacion_actual() or {}).items() if k_.split("_", 1)[1] in activas)
        resultado = snap.get("realizado", 0.0) if snap.get("hay_estado") else 0.0  # ganado o perdido ya cerrado
        falta = comprometido - (nuevo + max(0.0, resultado)) if snap.get("hay_estado") else 0.0
        if falta > 0.005 and snap.get("auto"):
            falta = 0  # en automático el bot saca la diferencia solo, de las partes que no tienen posición abierta
        if falta > 0.005:  # los montos guardados suman más que el capital nuevo: hay que bajarlos
            libre = max(0.0, nuevo + max(0.0, resultado) - comprometido)
            factor = max(0.0, 1 - falta / max(1e-9, comprometido))
            if not preguntar(self, t("Capital de cada modo"), t(
                    "Para bajar el capital de {m} de {a} a {b} hay que sacar {f} de las estrategias, porque sin asignar "
                    "hay solo {l}.", m=t(K.NOMBRE_MODO[K.MODO]), a=usd(efectivo), b=usd(nuevo), f=usd(falta),
                    l=usd(libre)) + "\n\n" + t(
                    "¿Bajar los montos de todas las estrategias en la misma proporción (cada uno queda en el {p} de lo que "
                    "tiene)? Las que tienen una posición abierta lo aplican cuando la cierran. Si preferís elegir vos qué "
                    "bajar, cancelá y cambiá los montos en Estrategias.", p=pct(factor * 100, 0)),
                    t("Bajar montos y guardar"), t("Cancelar")):
                self.sp_capital[K.MODO].setValue(efectivo)
                self.lbl_cap_res.setText(t("No se cambió el capital de {m}.", m=t(K.NOMBRE_MODO[K.MODO])))
                self.lbl_cap_res.setStyleSheet(f"font-size:13px; color:{MUTED}")
                return
            if snap.get("auto"):
                PT.guardar_auto(montos={a_: int(v * factor * 100) / 100 for a_, v in (snap.get("auto_montos") or {}).items()})
            else:
                asig = PT.asignacion_actual() or {}
                PT.guardar_asignacion({k_: int(v * factor * 100) / 100 for k_, v in asig.items()})
            PT.log(t("Montos de las estrategias bajados al {p} para bajar el capital a {b} USDT.", p=pct(factor * 100, 0),
                     b=num(nuevo)))
            self._montos_sucios = False
        for m, sp in self.sp_capital.items():
            caps[m] = round(float(sp.value()), 2)
        PT.guardar_ajustes(capital=caps)
        PT.configurar_modo(K.MODO)
        self._pintar_modo()
        if abs(nuevo - efectivo) >= 0.01:
            self.bot.revisar_ahora()
            QTimer.singleShot(2500, self.refrescar)
            self.lbl_cap_res.setText(t("Capital guardado. En {m} pasa de {a} a {b}.", m=t(K.NOMBRE_MODO[K.MODO]),
                                       a=usd(efectivo), b=usd(nuevo)) + " " +
                                     (t("La diferencia queda sin asignar: repartila en Estrategias.") if nuevo > efectivo
                                      else t("Se aplica en unos segundos.")))
        else:
            self.lbl_cap_res.setText(t("Capital guardado."))
        self.lbl_cap_res.setStyleSheet(f"font-size:13px; color:{GAIN}")

    def _guardar_y_repartir(self, activas=None):
        import auto as AU
        if PRUEBA:
            aviso(self, t("Modo prueba"), t("En modo prueba no se cambia el capital.")); return
        snap = self.snap or {}
        if snap.get("auto"):
            self._guardar_capital()
            aviso(self, t("Capital de cada modo"), t("En modo automático el bot ya reparte solo todo el capital entre las "
                                                     "estrategias que elige. Se guardó el capital."))
            return
        hist = self.mkt.historial
        regs = {a: an["regimen"] for a, an in self.mkt.analisis.items()}
        if not hist or len(regs) < len(K.SYMBOLS):
            aviso(self, t("Capital de cada modo"), t("Todavía no está lista la lectura del mercado o el historial de "
                                                     "estrategias (tarda unos minutos al abrir la app). Probá de nuevo en "
                                                     "un rato.")); return
        activas = activas or snap.get("activas") or []
        nuevo = round(float(self.sp_capital[K.MODO].value()), 2)
        total = max(0.0, nuevo + (snap.get("realizado", 0.0) if snap.get("hay_estado") else 0.0))
        montos, motivos = AU.montos_recomendados(hist, regs, activas, total, minimo=self._monto_minimo)
        if not montos or sum(montos.values()) <= 0:
            aviso(self, t("Capital de cada modo"), t("Con las estrategias activas y el capital elegido no se llega al "
                                                     "mínimo de Binance en ninguna moneda. Subí el capital o activá otras "
                                                     "estrategias.")); return
        txt_mot = {"empeora": t("viene empeorando"), "no_conviene": t("perdió en este tipo de mercado"),
                   "minimo": t("no llega al mínimo de Binance")}
        lineas, sin = [], []
        for a in K.SYMBOLS:
            for k in activas:
                c = f"{a}_{k}"
                if montos.get(c, 0) > 0:
                    lineas.append(f"• {a} {M.nombre_estrategia(k)}: {usd(montos[c])}")
                else:
                    sin.append(f"{a} {M.nombre_estrategia(k)} ({txt_mot.get(motivos.get(c), '—')})")
        msg = (t("Capital de {m}: {c}. Con el resultado ya cerrado, hay {d} para repartir.", m=t(K.NOMBRE_MODO[K.MODO]),
                 c=usd(nuevo), d=usd(total)) + "\n\n" + t(
                 "El bot recomienda repartirlo así, con más dinero para las estrategias que mejor funcionaron en el tipo de "
                 "mercado de hoy de cada moneda:") + "\n" + "\n".join(lineas) +
               (("\n\n" + t("Sin capital:") + " " + "; ".join(sin) + ".") if sin else "") + "\n\n" +
               t("Reemplaza los montos que tenías. Las partes con una posición abierta toman el monto nuevo cuando la "
                 "cierran. ¿Guardar?"))
        if not preguntar(self, t("Capital de cada modo"), msg, t("Guardar y repartir"), t("Cancelar")):
            return
        caps = PT.leer_ajustes().get("capital", {})
        for m_, sp in self.sp_capital.items():
            caps[m_] = round(float(sp.value()), 2)
        PT.guardar_ajustes(capital=caps)
        asig = {k_: 0.0 for k_ in (PT.asignacion_actual() or {})}
        asig.update(montos)
        PT.guardar_asignacion(asig)
        PT.configurar_modo(K.MODO)
        PT.log(t("Capital y montos repartidos como recomienda el bot: {l}.", l=", ".join(
            f"{k_} {num(v)}" for k_, v in montos.items() if v > 0)))
        self._montos_sucios = False
        self._pintar_modo()
        self.bot.revisar_ahora()
        QTimer.singleShot(2500, lambda: (self.refrescar(), self._llenar_montos(forzar=True)))
        self.lbl_cap_res.setText(t("Guardado y repartido. Se aplica en unos segundos; lo ves en Estrategias y Posiciones."))
        self.lbl_cap_res.setStyleSheet(f"font-size:13px; color:{GAIN}")

    def _revisar_capital(self):
        """Avisa si el capital guardado del modo no coincide con el que usa el bot."""
        snap = self.snap or {}
        if not snap.get("hay_estado") or not hasattr(self, "lbl_cap_aviso"):
            return
        efectivo, guardado = snap.get("base", K.INITIAL_CAPITAL), K.INITIAL_CAPITAL
        if abs(efectivo - guardado) >= 0.01:
            self.lbl_cap_aviso.setText(t(
                "Atención: en {m} tenés guardado {g}, pero el bot está usando {e} porque no hay suficiente capital sin "
                "asignar para sacar la diferencia. Tocá Guardar capital para bajar los montos de las estrategias, o "
                "bajalos vos en Estrategias.", m=t(K.NOMBRE_MODO[K.MODO]), g=usd(guardado), e=usd(efectivo)))
            self.lbl_cap_aviso.setVisible(True)
        else:
            self.lbl_cap_aviso.setVisible(False)

    def _cambiar_pref(self, clave, valor):
        actual = i18n.LANG if clave == "idioma" else TEMA
        PT.guardar_ajustes(**{clave: valor})
        if valor == actual:
            self.lbl_pref.setText(""); return
        self.lbl_pref.setText(t("Se aplica al reiniciar la aplicación.")); self.lbl_pref.setStyleSheet(f"color:{AMBER}")
        if preguntar(self, t("Preferencias"), t("Para aplicar el cambio hay que reiniciar la aplicación. El bot se detiene "
                                                 "unos segundos y vuelve a arrancar solo. ¿Reiniciar ahora?"),
                     t("Reiniciar ahora"), t("Más tarde")):
            self.reiniciar_app()

    def _cambiar_inicio(self, activar):
        r = inicio_windows(bool(activar))
        if r is None:
            self.lbl_pref.setText(t("No se pudo cambiar el inicio automático.")); self.lbl_pref.setStyleSheet(f"color:{LOSS}")
        else:
            self.lbl_pref.setText(t("El bot se abre solo al iniciar Windows.") if r else
                                  t("El bot ya no se abre solo al iniciar Windows."))
            self.lbl_pref.setStyleSheet(f"color:{GAIN}")

    def _riesgo_defecto(self):
        self.sp_riesgo.setValue(3); self.sp_limite.setValue(25); self.sp_espera.setValue(180)

    def _guardar_riesgo(self):
        if PRUEBA:
            aviso(self, t("Modo prueba"), t("En modo prueba no se cambia el riesgo.")); return
        r = dict(por_operacion=round(self.sp_riesgo.value() / 100, 4), limite_perdida=round(self.sp_limite.value() / 100, 4),
                 espera_limite=int(self.sp_espera.value()))
        if r["por_operacion"] > 0.03 + 1e-9 and not preguntar(
                self, t("Riesgo"), t("Vas a arriesgar {p} por operación, más que el 3 % probado. Una racha de pérdidas puede "
                                     "bajar la cuenta mucho más rápido. ¿Guardar igual?", p=pct(r["por_operacion"] * 100, 1)),
                t("Guardar"), t("Cancelar")):
            return
        PT.guardar_ajustes(riesgo=r)
        corriendo = self.bot.corriendo()
        self.bot.detener(); PT.configurar_modo(K.MODO)
        if corriendo:
            self.bot.iniciar()
        PT.log(t("Riesgo cambiado: {p} por operación, límite de pérdida {l}, espera de la orden límite {e} s.",
                 p=pct(r["por_operacion"] * 100, 1), l=pct(r["limite_perdida"] * 100, 0), e=r["espera_limite"]))
        self.lbl_riesgo_res.setText(t("Guardado y aplicado.")); self.lbl_riesgo_res.setStyleSheet(f"color:{GAIN}")
        self._pintar_modo()

    def _generar_ed25519(self, m):
        u = self.ui_claves[m]
        par = CL.cargar_privada_pendiente(m)
        if par and preguntar(self, t("Clave Ed25519"), t("Ya generaste una clave Ed25519 para este modo. ¿Querés ver la misma "
                                                          "clave pública o generar una nueva?"),
                             t("Ver la misma"), t("Generar una nueva")):
            pub = par[1]
        else:
            priv, pub = CL.generar_ed25519(); CL.guardar_privada_pendiente(m, priv, pub)
        u["pub"].setPlainText(pub.strip()); u["pub"].setVisible(True)
        QApplication.clipboard().setText(pub.strip())
        u["res"].setText(t("Clave pública copiada al portapapeles (la de arriba). En Binance: Crear API, elegí la opción "
                           "Autogenerada, pegá esta clave pública y confirmá. Después copiá la Clave de API que te muestra "
                           "Binance, pegala en el campo Clave de API de esta app, dejá vacía la clave secreta y tocá Guardar "
                           "claves. La clave privada queda solo en esta PC, cifrada."))
        u["res"].setStyleSheet(f"font-size:13px; color:{TEXT}")

    def _guardar_claves(self, m):
        u = self.ui_claves[m]
        k, sec = u["key"].text().strip(), u["sec"].text().strip()
        if len(k) >= 20 and not sec and CL.cargar_privada_pendiente(m):
            try:
                CL.completar_ed25519(m, k)
            except OSError as e:
                u["res"].setText(t("No se pudieron guardar:") + f" {e}"); u["res"].setStyleSheet(f"color:{LOSS}"); return
            u["key"].clear(); u["pub"].setVisible(False)
            u["res"].setText(t("Clave de API guardada junto con tu clave privada Ed25519. Tocá Probar conexión."))
            u["res"].setStyleSheet(f"color:{GAIN}"); self._pintar_modo(); return
        if len(k) < 20 or len(sec) < 20:
            u["res"].setText(t("Pegá la clave de API completa. Si la creaste con una clave Ed25519 de esta app, dejá vacía la "
                               "clave secreta; si Binance te dio una clave secreta, pegala también."))
            u["res"].setStyleSheet(f"color:{AMBER}"); return
        try:
            CL.guardar(m, k, sec)
        except OSError as e:
            u["res"].setText(t("No se pudieron guardar:") + f" {e}"); u["res"].setStyleSheet(f"color:{LOSS}"); return
        u["key"].clear(); u["sec"].clear()
        u["res"].setText(t("Claves guardadas y cifradas. Tocá Probar conexión.")); u["res"].setStyleSheet(f"color:{GAIN}")
        self._pintar_modo()

    def _borrar_claves(self, m):
        if preguntar(self, t("Borrar claves"), t("¿Borrar las claves de {m} guardadas en esta PC?", m=t(K.NOMBRE_MODO[m])),
                     t("Borrar"), t("Cancelar")):
            CL.borrar(m); self._pintar_modo(); self.ui_claves[m]["res"].setText(t("Claves borradas."))

    def _probar(self, m, que):
        u = self.ui_claves[m]
        cred = CL.cargar(m)
        if not cred:
            u["res"].setText(t("Primero guardá las claves.")); u["res"].setStyleSheet(f"color:{AMBER}"); return
        if que == "ordenes" and not preguntar(
                self, t("Probar órdenes"), t("Se va a comprar la cantidad mínima de SOL en la cuenta demo, poner un stop, "
                                             "cancelarlo y cerrar la posición. Tarda menos de un minuto. ¿Seguir?"),
                t("Probar"), t("Cancelar")):
            return
        for b in u["botones"].values():
            b.setEnabled(False)
        u["res"].setText(t("Conectando con Binance…")); u["res"].setStyleSheet(f"color:{MUTED}")
        self.trabajo[m] = None
        pasos = []

        def tarea():
            try:
                br = LV.Broker(m, *cred)
                sal = br.saldo()
                mins = {a: br.minimos(sym)["costo"] for a, sym in K.SYMBOLS.items()}
                self._minimos = mins
                txt = t("Conexión correcta. Saldo de futuros: {s} (libre {l}). Tamaño mínimo por orden: {m}.",
                        s=usd(sal["total"]), l=usd(sal["libre"]), m=", ".join(f"{a} {usd(c, 0)}" for a, c in mins.items()))
                if que == "ordenes":
                    LV.prueba_ordenes(br, lambda x: pasos.append(x.strip()))
                    txt = t("Prueba de órdenes correcta:") + "\n" + "\n".join(pasos)
                self.trabajo[m] = (True, txt)
            except Exception as e:
                self.trabajo[m] = (False, (t("Falló:") + f" {type(e).__name__}: {e}")[:400] +
                                   ("\n" + "\n".join(pasos) if pasos else ""))

        threading.Thread(target=tarea, daemon=True).start()

    def _ver_trabajo(self):
        self._pintar_actualizacion()
        for m, r in list(self.trabajo.items()):
            if r is None:
                continue
            ok, txt = r
            u = self.ui_claves[m]
            u["res"].setText(txt); u["res"].setStyleSheet(f"font-size:13px; color:{GAIN if ok else LOSS}")
            for b in u["botones"].values():
                b.setEnabled(True)
            if ok:
                PT.guardar_ajustes(**{f"probado_{m}": time.time()})
            del self.trabajo[m]
        st = A.leer_estado(DATOS) if K.MODO != "simulado" else None
        if st and st.get("frenado"):
            self.lbl_seg.setText(t("El bot está FRENADO por el límite de pérdida: no abre operaciones nuevas."))
            self.lbl_seg.setStyleSheet(f"font-size:12px; color:{LOSS}")
        else:
            self.lbl_seg.setText("")

    def _cambiar_modo(self, nuevo):
        actual = K.MODO
        if nuevo == actual:
            self._pintar_modo(); return
        if PRUEBA:
            aviso(self, t("Modo prueba"), t("En modo prueba no se cambia el modo.")); self._pintar_modo(); return
        if nuevo != "simulado" and not CL.cargar(nuevo):
            aviso(self, t("Modo de operación"), t("Primero cargá y probá las claves de {m}, más abajo en esta misma página.",
                                                  m=t(K.NOMBRE_MODO[nuevo])))
            self._pintar_modo(); return
        if nuevo != "simulado" and not PT.leer_ajustes().get(f"probado_{nuevo}"):
            aviso(self, t("Modo de operación"), t("Primero tocá Probar conexión y verificá que funcione."))
            self._pintar_modo(); return
        abiertas = (self.snap or {}).get("abiertas", [])
        aviso_pos = ("\n\n" + t("Atención: hay {n} posiciones abiertas en {m}.", n=len(abiertas), m=t(K.NOMBRE_MODO[actual])) + " " +
                     (t("Siguen en Binance con su stop, pero el bot no las va a manejar hasta que vuelvas a este modo.")
                      if actual != "simulado" else t("Quedan congeladas hasta que vuelvas a este modo."))) if abiertas else ""
        if nuevo == "real":
            cap = float(PT.leer_ajustes().get("capital", {}).get("real", 100))
            msg = (t("Vas a operar con DINERO REAL en Binance Futuros.") + "\n\n" +
                   t("El bot va a usar hasta {c} de tu cuenta, con apalancamiento de hasta {x}x y {r} de riesgo por "
                     "operación. Los resultados pasados y del modo demo no garantizan resultados futuros y podés perder "
                     "dinero.", c=usd(cap), x=num(K.MAX_LEVERAGE, 0), r=pct(K.RISK_PER_TRADE * 100, 1)) +
                   aviso_pos + "\n\n" + t("Para confirmar, escribí REAL:"))
            txt, ok = pedir_texto(self, t("Operar con dinero real"), msg)
            if not ok or txt.strip().upper() != "REAL":
                self._pintar_modo(); return
        elif not preguntar(self, t("Cambiar de modo"), t("¿Pasar a {m}?", m=t(K.NOMBRE_MODO[nuevo])) + aviso_pos,
                           t("Cambiar"), t("Cancelar")):
            self._pintar_modo(); return
        self.bot.detener()
        PT.guardar_ajustes(modo=nuevo); PT.configurar_modo(nuevo)
        PT.STATUS.update(ultima_revision=None, ultimo_error=None)
        self._dec_firma = None; self._montos_sucios = False; self._minimos = None
        self.bot.iniciar()
        PT.log(t("Modo cambiado de {a} a {b}.", a=t(K.NOMBRE_MODO[actual]), b=t(K.NOMBRE_MODO[nuevo])))
        self._pintar_modo(); self.refrescar()

    def _con_bot_detenido(self, titulo, accion):
        """Detiene el bot, hace la acción con una conexión propia y lo vuelve a arrancar."""
        cred = CL.cargar(K.MODO)
        if not cred:
            return
        self.bot.detener()
        try:
            r = accion(LV.Broker(K.MODO, *cred), PT.load_state())
            aviso(self, titulo, r)
        except Exception as e:
            aviso(self, titulo, (t("No se pudo completar:") + f" {type(e).__name__}: {e}")[:400], True)
        self.bot.iniciar(); self.refrescar()

    def _cerrar_todo(self):
        if not preguntar(self, t("Cerrar todo"), t("¿Cerrar a mercado todas las posiciones del bot en {m} y cancelar sus stops?",
                                                   m=t(K.NOMBRE_MODO[K.MODO])), t("Cerrar todo"), t("Cancelar")):
            return
        self._con_bot_detenido(t("Cerrar todo"), lambda br, st: t("Se cerraron {n} posiciones.", n=LV.cerrar_todo(br, st)))

    def _reanudar(self):
        st = A.leer_estado(".")
        if not st or not st.get("frenado"):
            aviso(self, t("Reanudar"), t("El bot no está frenado.")); return
        if not preguntar(self, t("Reanudar"), t("¿Permitir que el bot vuelva a abrir operaciones? El límite de pérdida se "
                                                 "vuelve a medir desde el saldo actual del bot."), t("Reanudar"), t("Cancelar")):
            return
        self.bot.detener()
        st = PT.load_state(); st["frenado"] = False
        st["ref_limite"] = sum(v["equity"] for v in st["sleeves"].values()) + st.get("libre", 0.0)
        PT.save_state(st); PT.log(t("Bot reanudado después del límite de pérdida."))
        self.bot.iniciar(); self.refrescar()

    # ---------- acciones
    def _abrir(self, rel):
        try:
            os.startfile(os.path.abspath(rel))
        except (OSError, AttributeError):
            aviso(self, t("Bot de trading"), t("Todavía no existe {f}.", f=rel))

    def alternar_bot(self):
        if self.bot.corriendo():
            if not preguntar(self, t("Detener bot"), t("¿Detener el bot? Mientras esté detenido no abre ni cierra operaciones "
                                                        "(las posiciones abiertas quedan como están, con su stop)."),
                             t("Detener"), t("Cancelar")):
                return
            self.btn_bot.setEnabled(False); QApplication.processEvents()
            self.bot.detener(); self.btn_bot.setEnabled(True)
        else:
            self.bot.iniciar()
        self.tick()

    def reiniciar_app(self):
        if PRUEBA:
            aviso(self, t("Modo prueba"), t("En modo prueba no se reinicia la aplicación.")); return
        args = [a for a in sys.argv[1:] if a not in ("--minimizado", "--reinicio")]
        exe = sys.executable
        if exe.lower().endswith("python.exe") and os.path.exists(exe[:-10] + "pythonw.exe"):
            exe = exe[:-10] + "pythonw.exe"
        subprocess.Popen([exe, os.path.abspath(__file__), "--reinicio"] + args, cwd=os.getcwd())
        if self.salir_fn:
            self.salir_fn()

    # ---------- refresco
    def tick(self):
        s, ahora = PT.STATUS, time.time()
        corriendo = self.bot.corriendo()
        estado = s.get("estado") if corriendo else "detenido"
        hora_ini = int(ahora // 3600 * 3600)
        frac = (ahora - hora_ini) / 3600
        vela = t("Vela de {a} a {b}", a=f"{datetime.fromtimestamp(hora_ini):%H:%M}", b=f"{datetime.fromtimestamp(hora_ini + 3600):%H:%M}")
        prox = s.get("proxima_revision")
        if estado == "detenido":
            err = s.get("ultimo_error")
            self.reloj.set(frac, t("Detenido"), t("Mirá el motivo abajo a la izquierda") if err else
                           t("Tocá Iniciar bot para que vuelva a revisar"), LOSS if err else MUTED)
            col, txt = (LOSS, t("Bot detenido por un error")) if err else (MUTED, t("Bot detenido"))
        elif estado == "revisando" or not prox:
            self.reloj.set(frac, t("Revisando"), vela, ACCENT)
            col, txt = ACCENT, t("Revisando el mercado")
        else:
            rest = max(0, prox - ahora)
            mm, ss = divmod(int(rest), 60)
            centro = f"{mm}:{ss:02d}" if mm < 60 else f"{mm // 60} h {mm % 60:02d}"
            if estado == "error":
                self.reloj.set(1 - rest / 60, centro, t("Reintentando la conexión"), AMBER)
                col, txt = AMBER, t("Sin conexión, reintentando")
            else:
                self.reloj.set(frac, centro, t("para la próxima revisión") + "\n" + vela, ACCENT)
                col, txt = GAIN, t("Corriendo")
        self.punto.setStyleSheet(f"background:{col}; border-radius:5px;")
        self.lbl_estado.setText(txt)
        ult = s.get("ultima_revision")
        sub = (t("Última revisión del mercado: {h}", h=f"{datetime.fromtimestamp(ult):%H:%M}") if ult
               else t("Todavía no revisó el mercado"))
        if estado in ("error", "detenido") and s.get("ultimo_error"):
            sub += f"\n{s['ultimo_error'][:160]}"
        self.lbl_estado_sub.setText(sub)
        self.btn_revisar.setEnabled(corriendo and estado != "revisando")
        self.btn_bot.setText(t("Detener bot") if corriendo else t("Iniciar bot"))
        self.btn_bot.setProperty("rol", "peligro" if corriendo else "primario")
        self.btn_bot.style().unpolish(self.btn_bot); self.btn_bot.style().polish(self.btn_bot)
        if self.feed.updated:
            seg = int(ahora - self.feed.updated)
            self.lbl_precios_upd.setText(t("Binance Futuros, hace {x}", x=f"{seg}{NB}s" if seg < 120 else A.fmt_dur(seg)))
        elif self.feed.error:
            self.lbl_precios_upd.setText(t("No se pudieron leer los precios. Reintentando."))

    def refrescar(self):
        try:
            self.snap = A.snapshot(DATOS, dict(self.feed.prices), PT.STATUS)
        except Exception:
            _log_crash(*sys.exc_info())
            return
        s = self.snap
        self.lbl_saldo.setText(usd(s["saldo"]))
        ini = s.get("inicio")
        desde = (" " + t("desde que arrancó ({f})", f=f"{datetime.fromisoformat(ini):%d/%m %H:%M}")) if ini else ""
        self.lbl_rend.setText(t("{p} sobre el capital de {b}", p=pct(s["rendimiento_pct"], 2, True), b=usd(s["base"])) + desde)
        self.lbl_rend.setStyleSheet(f"font-size:14px; color:{color_de(s['rendimiento_pct'])}")
        for k, val in (("real", s["realizado"]), ("abierto", s["abierto"])):
            self.kpi[k].setText(usd(val, 2, True))
            self.kpi[k].setStyleSheet(f"font-size:17px; font-weight:600; color:{color_de(val)}")
        self.kpi["libre"].setText(usd(s["libre"]))
        self.kpi["libre"].setStyleSheet(f"font-size:17px; font-weight:600; color:{AMBER if s['libre'] > 0.5 else TEXT}")
        self.kpi["nops"].setText(str(s["resumen_ops"]["n"]))
        for a, (pl, cl) in self.lbl_precios.items():
            d = s["precios"].get(a)
            if d:
                pl.setText(A.fmt_precio(d["precio"]))
                ch = d.get("cambio")
                cl.setText(t("{v} en 24 h", v=pct(ch, 1, True)) if ch is not None else "")
                cl.setStyleSheet(f"font-size:12px; color:{color_de(ch)}")
        self._pintar_grafico()
        self._llenar_abiertas(); self._llenar_ultimas(); self._llenar_pos(); self._llenar_ops(); self._llenar_log()
        self._llenar_decisiones(); self._llenar_estrategias(); self._llenar_avisos(); self._llenar_lab(); self._revisar_capital()
        self._actualizar_bandeja(); self._notificar()

    def _pintar_grafico(self):
        if not self.snap:
            return
        pts = self.snap["curva"]
        if self.rango and pts:
            lim = time.time() - self.rango
            pts = [p for p in pts if p[0] >= lim] or pts[-2:]
        self.grafico.set_puntos(pts, self.snap["base"])

    @staticmethod
    def _vaciar(box):
        while box.count():
            it = box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                Ventana._vaciar(it.layout())

    def _fila_resumen(self, izq, izq_sub, der, der_col, der_sub=""):
        w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0, 6, 0, 6); h.setSpacing(12)
        a = QVBoxLayout(); a.setSpacing(1)
        a.addWidget(lbl(izq, size=14, weight=600)); a.addWidget(lbl(izq_sub, rol="muted", size=12, wrap=True))
        h.addLayout(a, 1)
        b = QVBoxLayout(); b.setSpacing(1)
        x = lbl(der, size=14, weight=600, color=der_col); x.setAlignment(Qt.AlignRight); b.addWidget(x)
        if der_sub:
            y = lbl(der_sub, rol="muted", size=12); y.setAlignment(Qt.AlignRight); b.addWidget(y)
        h.addLayout(b)
        return w

    def _llenar_abiertas(self):
        self._vaciar(self.box_abiertas)
        ab = self.snap["abiertas"]
        if not ab:
            self.box_abiertas.addWidget(lbl(t("Sin posiciones abiertas. El bot entra cuando aparece una señal en alguna de "
                                              "las estrategias activas."), rol="muted", size=13, wrap=True))
            return
        for f in ab:
            lado = t("compra") if f["lado"] == "long" else t("venta en corto")
            sub = t("{e}, entrada {a}, stop {s}", e=f["estrategia"], a=A.fmt_precio(f["entrada"]), s=A.fmt_precio(f["stop"]))
            der = usd(f["pnl"], 2, True) if f["pnl"] is not None else "—"
            dsub = pct(f["pnl_pct"], 2, True) if f["pnl_pct"] is not None else ""
            self.box_abiertas.addWidget(self._fila_resumen(f"{f['activo']} {lado}", sub, der, color_de(f["pnl"]), dsub))

    def _llenar_ultimas(self):
        self._vaciar(self.box_ultimas)
        ops = self.snap["operaciones"][:5]
        if not ops:
            self.box_ultimas.addWidget(lbl(t("Todavía no hay operaciones cerradas."), rol="muted", size=13)); return
        for o in ops:
            lado = t("compra") if o["lado"] == "long" else t("venta en corto")
            sub = t("{e}, cerró {f} ({m})", e=o["estrategia"], f=A.fecha_corta(o["salida_t"]), m=o["motivo"].lower())
            self.box_ultimas.addWidget(self._fila_resumen(f"{o['activo']} {lado}", sub, usd(o["pnl"], 2, True),
                                                          color_de(o["pnl"])))

    def _llenar_pos(self):
        tb, filas, ahora = self.tab_pos, self.snap["posiciones"], time.time()
        tb.setRowCount(len(filas))
        for r, f in enumerate(filas):
            celda(tb, r, 0, f["activo"], bold=True)
            celda(tb, r, 1, f["estrategia"])
            celda(tb, r, 2, usd(f["asignado"]) if f.get("activa", True) else "—", MUTED)
            celda(tb, r, 3, usd(f["capital"]), color_de(f["resultado"]) if abs(f["resultado"]) > 1e-9 else None)
            if f["lado"]:
                est, col = (t("Compra") if f["lado"] == "long" else t("Venta en corto")), (GAIN if f["lado"] == "long" else LOSS)
            elif f["pendiente"]:
                est, col = t("Orden pendiente"), AMBER
            elif f["capital"] <= 1e-9:
                est, col = t("Sin monto asignado"), MUTED
            else:
                est, col = t("Esperando señal"), MUTED
            if not f.get("activa", True):
                est += " " + t("(desactivada)")
            celda(tb, r, 4, est, col)
            celda(tb, r, 5, A.fmt_precio(f["entrada"]) if f["lado"] else "—")
            celda(tb, r, 6, A.fmt_precio(f["precio"]))
            celda(tb, r, 7, A.fmt_precio(f["stop"]) if f["lado"] else "—")
            celda(tb, r, 8, pct(f["dist_stop_pct"]) if f["dist_stop_pct"] is not None else "—")
            celda(tb, r, 9, usd(f["tamano"]) if f["tamano"] else "—")
            celda(tb, r, 10, usd(f["pnl"], 2, True) if f["pnl"] is not None else "—",
                  color_de(f["pnl"]) if f["pnl"] is not None else None, bold=f["pnl"] is not None)
            celda(tb, r, 11, A.fmt_dur(ahora - f["abierta_desde"]) if f["abierta_desde"] else "—")

    def _llenar_ops(self):
        s = self.snap["resumen_ops"]
        self.op_stats["n"].setText(str(s["n"]))
        self.op_stats["pct"].setText(pct(s["pct"], 0) if s["pct"] is not None else "—")
        for k in ("pnl", "mejor", "peor"):
            v = s[k]
            self.op_stats[k].setText(usd(v, 2, True) if v is not None else "—")
            self.op_stats[k].setStyleSheet(f'font-size:20px; font-weight:600; font-family:"{FONT}"; '
                                           f'color:{color_de(v) if v is not None else TEXT}')
        ops, tb = self.snap["operaciones"], self.tab_ops
        self.stack_ops.setCurrentIndex(1 if ops else 0)
        tb.setRowCount(len(ops))
        for r, o in enumerate(ops):
            celda(tb, r, 0, A.fecha_corta(o["salida_t"])); celda(tb, r, 1, o["activo"], bold=True); celda(tb, r, 2, o["estrategia"])
            celda(tb, r, 3, t("Compra") if o["lado"] == "long" else t("Venta en corto"))
            celda(tb, r, 4, A.fmt_precio(o["entrada"])); celda(tb, r, 5, A.fmt_precio(o["salida"]))
            celda(tb, r, 6, o["motivo"]); celda(tb, r, 7, usd(o["pnl"], 2, True), color_de(o["pnl"]), True)
            celda(tb, r, 8, usd(o["capital"]))

    def _llenar_log(self):
        lineas = A.leer_log(DATOS, 500)
        if lineas and len(lineas) == self._log_n and self.txt_log.toPlainText().endswith(lineas[-1]):
            return
        sb = self.txt_log.verticalScrollBar(); abajo = sb.value() >= sb.maximum() - 4
        self.txt_log.setPlainText("\n".join(lineas)); self._log_n = len(lineas)
        if abajo:
            sb.setValue(sb.maximum())

    # ---------- bandeja y notificaciones
    def set_bandeja(self, tray):
        self.tray = tray

    def _actualizar_bandeja(self):
        if not getattr(self, "tray", None) or not self.snap:
            return
        s = self.snap
        self.tray.setToolTip(t("Bot de trading: {s} ({p})", s=usd(s["saldo"]), p=pct(s["rendimiento_pct"], 2, True)))
        self.tray.setIcon(icono_app(GAIN if s["saldo"] >= s["base"] else LOSS))

    def _notificar(self):
        dec = self.snap["decisiones"]
        if not dec:
            return
        hora = dec[0]["hora"]
        if self._ultima_notif is None:  # al abrir la app no avisa lo viejo
            self._ultima_notif = hora; return
        if hora == self._ultima_notif:
            return
        self._ultima_notif = hora
        if not getattr(self, "tray", None) or not PT.leer_ajustes().get("notificaciones", True):
            return
        hechos = [f"{it['activo']} {it['estrategia']}: {it['texto']}" for it in dec[0]["items"]
                  if it["accion"] in ("abre", "cierra")]
        if hechos:
            self.tray.showMessage(t("El bot operó"), "\n".join(hechos)[:240], QSystemTrayIcon.Information, 8000)

    def mostrar(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    def closeEvent(self, e):
        if self.saliendo:
            e.accept(); return
        e.ignore(); self.hide()
        if not self.aviso_bandeja and getattr(self, "tray", None):
            self.tray.showMessage(t("El bot sigue corriendo"), t("Quedó en el ícono junto a la hora. Para cerrarlo del todo, "
                                                                 "usá Salir en el menú del ícono."),
                                  QSystemTrayIcon.Information, 5000)
            self.aviso_bandeja = True


# ------------------------------------------------------------------ arranque
def _esperar_instancia_anterior(nombre, segundos=40):
    """Al reiniciar, espera a que la instancia anterior termine de cerrarse."""
    fin = time.time() + segundos
    while time.time() < fin:
        s = QLocalSocket(); s.connectToServer(nombre)
        if not s.waitForConnected(200):
            return
        s.abort()
        time.sleep(0.5)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    try:
        app.setStyleSheet(QSS + qss_flechas())
    except Exception:
        app.setStyleSheet(QSS)
    f = QFont(FONT_TXT); f.setPixelSize(13); app.setFont(f)

    prueba = PRUEBA  # solo la ventana, sin arrancar el bot (para revisar la interfaz)
    nombre = "BotTradingV2App" + ("Prueba" if prueba else "")
    if "--reinicio" in sys.argv:
        _esperar_instancia_anterior(nombre)
    sock = QLocalSocket(); sock.connectToServer(nombre)
    if sock.waitForConnected(300):  # ya hay una ventana abierta: la muestra y sale
        sock.write(b"mostrar"); sock.flush(); sock.waitForBytesWritten(300)
        return
    _mutex = None
    if not prueba:  # bloquea también a la versión anterior (tray_bot.py)
        import ctypes
        k32 = ctypes.windll.kernel32
        fin = time.time() + (40 if "--reinicio" in sys.argv else 0)
        while True:
            _mutex = k32.CreateMutexW(None, False, "Global\\BotTradingV2Paper")
            if k32.GetLastError() != 183:
                break
            k32.CloseHandle(_mutex)
            if time.time() >= fin:
                aviso(None, t("Bot de trading"), t("Hay otra versión del bot corriendo. Cerrala desde el ícono junto a la "
                                                   "hora (Salir) y volvé a abrir esta aplicación."), True)
                return
            time.sleep(0.5)
    QLocalServer.removeServer(nombre)
    server = QLocalServer(); server.listen(nombre)

    PT.configurar_modo(PT.leer_ajustes().get("modo", "simulado") if not prueba else "simulado")
    bot, feed, mkt = Bot(), PriceFeed(), MarketWorker()
    feed.start(); mkt.start()
    if prueba:  # muestra la cuenta regresiva real sin arrancar otro bot
        bot.corriendo = lambda: True
        nxt = time.time() // 3600 * 3600 + 3600 + 20
        PT.STATUS.update(estado="corriendo", proxima_revision=nxt, ultima_revision=nxt - 3600)
    else:
        bot.iniciar()
    win = Ventana(bot, feed, mkt)

    tray = QSystemTrayIcon(icono_app(), app)
    menu = QMenu()
    a_abrir = QAction(t("Abrir"), menu); a_abrir.triggered.connect(win.mostrar)
    a_rev = QAction(t("Revisar ahora"), menu); a_rev.triggered.connect(bot.revisar_ahora)

    def salir():
        bot.detener(); feed.stop.set(); mkt.stop.set(); win.saliendo = True; tray.hide()
        server.close(); app.quit()

    win.salir_fn = salir
    a_salir = QAction(t("Salir (detiene el bot)"), menu); a_salir.triggered.connect(salir)
    for a in (a_abrir, a_rev):
        menu.addAction(a)
    menu.addSeparator(); menu.addAction(a_salir)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda r: win.mostrar() if r in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) else None)
    tray.show(); win.set_bandeja(tray)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), win.mostrar()))

    if "--minimizado" not in sys.argv:
        win.show()
    app.aboutToQuit.connect(lambda: (bot.detener(), feed.stop.set()))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
