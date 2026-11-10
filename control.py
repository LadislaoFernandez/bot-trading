"""Bot de trading — control remoto para Windows.

Se conecta al bot que corre en el servidor (Oracle Cloud) con el código de conexión, y muestra todo lo de la app:
resumen, posiciones, operaciones, estrategias y piloto, avisos y registro. Desde acá se puede prender o apagar el bot y el
piloto, cambiar el riesgo y el capital, manejar el laboratorio y actualizar el servidor.

  pythonw control.py
"""
import os
import subprocess
import sys
import threading
import time
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

import app as U  # noqa: E402  (estilos y componentes de la app de escritorio)
from app import (ACCENT, AMBER, FONT, FONT_TXT, GAIN, LOSS, MUTED, NB, QSS, TEXT, GraficoCapital, SinRueda,  # noqa: E402
                 aviso, boton, celda, chip, color_de, con_pasos, icono_app, lbl, panel, pct, preguntar, qss_flechas,
                 scroll, tabla, usd)
from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QFont, QIcon  # noqa: E402
from PySide6.QtNetwork import QLocalSocket  # noqa: E402
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout,  # noqa: E402
                               QHBoxLayout, QInputDialog, QLineEdit, QMainWindow, QPlainTextEdit, QPushButton,
                               QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

import cliente_api as C  # noqa: E402
import config as K  # noqa: E402
import mercado as M  # noqa: E402
from i18n import num, t  # noqa: E402

ARCHIVO_CODIGO = "control_codigo.dat"


# ------------------------------------------------------------------ código de conexión guardado (cifrado en Windows)
def leer_codigo():
    import claves as CL
    try:
        with open(ARCHIVO_CODIGO, "rb") as f:
            return CL._desproteger(f.read()).decode("utf-8")
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def guardar_codigo(codigo):
    import claves as CL
    CL._escribir(ARCHIVO_CODIGO, CL._proteger(codigo.encode("utf-8")))


def pedir_codigo(parent, actual=""):
    while True:
        txt, ok = QInputDialog.getText(parent, t("Conectar con el servidor"), t(
            "Pegá el código de conexión del servidor (empieza con BOT1-). Lo muestra el servidor al instalarlo, o con el "
            "comando: venv/bin/python servidor.py codigo"), QLineEdit.Normal, actual)
        if not ok:
            return None
        try:
            C.leer_codigo(txt)
        except ValueError as e:
            aviso(parent, t("Código de conexión"), str(e), True); actual = txt; continue
        try:
            C.Cliente(txt).estado()
        except (C.ErrorConexion, C.ErrorServidor) as e:
            if not preguntar(parent, t("Código de conexión"), t("No se pudo conectar:") + f" {e}\n\n" +
                             t("¿Guardarlo igual (por ejemplo, si el servidor todavía no está prendido)?"),
                             t("Guardar igual"), t("Probar otro")):
                actual = txt; continue
        guardar_codigo("".join(txt.split()))
        return "".join(txt.split())


# ------------------------------------------------------------------ limpieza de la app de escritorio anterior
# El bot ahora corre en el servidor: de la app vieja quedan su inicio automático, sus accesos directos, sus datos locales
# y sus lanzadores. El código queda porque este control remoto usa sus componentes (y está respaldado en el repositorio).
DATOS_APP_VIEJA = ["alertas.json", "bot.log", "bot_demo.log", "bot_real.log", "capital_demo.csv", "capital_horario.csv",
                   "capital_real.csv", "claves_demo.dat", "claves_real.dat", "ed25519_demo.dat", "ed25519_real.dat",
                   "decisiones.jsonl", "decisiones_demo.jsonl", "decisiones_real.jsonl", "estado_bot.json",
                   "estado_demo.json", "estado_real.json", "historial_estrategias.json", "laboratorio.log",
                   "laboratorio_estado.json", "operaciones.csv", "operaciones_demo.csv", "operaciones_real.csv",
                   "app_error.log", "iniciar_bot.bat", "iniciar_oculto.vbs", "_buscar_python.bat",
                   "instalar_servidor.sh"]
CARPETAS_APP_VIEJA = ["candidatas", "datos_lab", "mis_estrategias"]


def limpiar_app_vieja():
    """Saca de Windows lo que queda de la app de escritorio (solo si no está abierta). Devuelve lo que borró."""
    import shutil
    if os.name != "nt" or app_local_abierta():
        return []
    hecho = []
    try:
        import winreg
        clave = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, clave, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            try:
                winreg.QueryValueEx(k, "BotTradingV2")
                winreg.DeleteValue(k, "BotTradingV2"); hecho.append("inicio automático")
            except FileNotFoundError:
                pass
    except OSError:
        pass
    perfil = os.environ.get("USERPROFILE", "")
    accesos = [os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs",
                            "Bot de trading.lnk")]
    for esc in ("Desktop", "Escritorio", os.path.join("OneDrive", "Desktop"), os.path.join("OneDrive", "Escritorio")):
        accesos.append(os.path.join(perfil, esc, "Bot de trading.lnk"))
    for x in accesos + DATOS_APP_VIEJA:
        try:
            if os.path.isfile(x):
                os.remove(x); hecho.append(os.path.basename(x))
        except OSError:
            pass
    ajustes = U._ajustes_iniciales()
    if set(ajustes) - {"idioma"}:  # de los ajustes de la app vieja, este control solo usa el idioma
        try:
            with open("ajustes.json", "w", encoding="utf-8") as f:
                f.write('{"idioma": "%s"}' % ajustes.get("idioma", "es"))
            hecho.append("ajustes.json")
        except OSError:
            pass
    for c in CARPETAS_APP_VIEJA:
        if os.path.isdir(c):
            shutil.rmtree(c, ignore_errors=True); hecho.append(c)
    return hecho


def app_local_abierta():
    s = QLocalSocket(); s.connectToServer("BotTradingV2App")
    ok = s.waitForConnected(200)
    s.abort()
    return ok


# ------------------------------------------------------------------ ventana
class Control(QMainWindow):
    def __init__(self, codigo):
        super().__init__()
        self.cliente, self.datos, self.error, self.version_datos = C.Cliente(codigo), None, None, 0
        self.pintado, self.detalles = -1, {}
        self.setWindowTitle(t("Bot de trading — control remoto"))
        self.setWindowIcon(QIcon("app_icon.ico") if os.path.exists("app_icon.ico") else icono_app())
        geo = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1380, int(geo.width() * 0.85)), min(900, int(geo.height() * 0.88)))
        self.setMinimumSize(1000, 660)
        raiz = QWidget(); self.setCentralWidget(raiz)
        hl = QHBoxLayout(raiz); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)
        hl.addWidget(self._lateral())
        self.paginas = QStackedWidget(); self.paginas.setObjectName("pagina")
        hl.addWidget(self.paginas, 1)
        for crear in (self._pag_resumen, self._pag_posiciones, self._pag_operaciones, self._pag_estrategias,
                      self._pag_avisos, self._pag_decisiones, self._pag_registro, self._pag_servidor):
            self.paginas.addWidget(crear())
        self.nav[0].setChecked(True)
        self.parar = threading.Event()
        threading.Thread(target=self._sondeo, daemon=True).start()
        self.reiniciar_pendiente = False
        if os.environ.get("QT_QPA_PLATFORM") != "offscreen" and not os.environ.get("BOT_SIN_ACTUALIZAR"):
            threading.Thread(target=self._auto_actualizar, daemon=True).start()
        self.t = QTimer(self); self.t.timeout.connect(self._pintar); self.t.start(700)

    # ---------- actualización automática de esta app (la del servidor la hace el servidor)
    def _auto_actualizar(self):
        import actualizador as AC
        self.parar.wait(20)  # deja arrancar la ventana primero
        while not self.parar.is_set():
            try:
                info = AC.buscar()
                if info:
                    self.lbl_app.setText(t("Actualizando a {v}…", v=info["version"]))
                    AC.instalar(info, carpeta=os.getcwd())
                    self.reiniciar_pendiente = True
                    return
            except Exception as e:  # sin internet o GitHub caído: reintenta en una hora
                print("actualización:", type(e).__name__, e)
            self.parar.wait(3600)

    def _reiniciar(self):
        exe = sys.executable
        if exe.lower().endswith("python.exe") and os.path.exists(exe[:-10] + "pythonw.exe"):
            exe = exe[:-10] + "pythonw.exe"
        subprocess.Popen([exe, os.path.abspath(__file__)], cwd=os.getcwd())
        self.parar.set()
        QApplication.quit()

    # ---------- datos (en segundo plano)
    def _sondeo(self):
        prox_det = 0
        while not self.parar.is_set():
            try:
                self.datos, self.error = self.cliente.estado(), None
                self.version_datos += 1
                if time.time() >= prox_det:
                    for q in ("curva", "operaciones"):
                        self.detalles[q] = self.cliente.detalle(q)
                    prox_det = time.time() + 60
                if self.paginas.currentIndex() == 5:
                    self.detalles["decisiones"] = self.cliente.detalle("decisiones")
                if self.paginas.currentIndex() == 6:
                    self.detalles["registro"] = self.cliente.detalle("registro")
            except (C.ErrorConexion, C.ErrorServidor) as e:
                self.error = str(e); self.version_datos += 1
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"; self.version_datos += 1
            self.parar.wait(5)

    def _accion(self, nombre, ok_msg=None, **datos):
        """Manda una acción al servidor sin trabar la ventana; avisa el resultado."""
        def tarea():
            try:
                r = self.cliente.accion(nombre, **datos)
                self._resultado = (True, ok_msg or "", r)
            except (C.ErrorConexion, C.ErrorServidor) as e:
                self._resultado = (False, str(e), None)
        self._resultado = None
        threading.Thread(target=tarea, daemon=True).start()

        def esperar():
            if self._resultado is None:
                QTimer.singleShot(200, esperar); return
            ok, msg, r = self._resultado
            if not ok:
                aviso(self, t("Servidor"), msg, True)
            elif msg:
                aviso(self, t("Servidor"), msg)
            self.pintado = -1
        QTimer.singleShot(200, esperar)

    # ---------- lateral
    def _lateral(self):
        w = QFrame(); w.setObjectName("lateral"); w.setFixedWidth(232)
        v = QVBoxLayout(w); v.setContentsMargins(14, 20, 14, 16); v.setSpacing(4)
        head = QHBoxLayout(); head.setSpacing(10)
        ic = lbl(); ic.setPixmap(icono_app().pixmap(32, 32)); head.addWidget(ic, 0, Qt.AlignTop)
        tv = QVBoxLayout(); tv.setSpacing(1)
        tv.addWidget(lbl(t("Bot de trading"), size=16, weight=600, family=FONT))
        self.lbl_modo = lbl(t("Control remoto"), size=12, wrap=True); tv.addWidget(self.lbl_modo)
        self.lbl_app = lbl(t("App {v}", v=K.VERSION), rol="muted", size=11); tv.addWidget(self.lbl_app)
        head.addLayout(tv, 1); v.addLayout(head); v.addSpacing(22)
        self.nav, grupo = [], QButtonGroup(self)
        for i, n in enumerate([t("Resumen"), t("Posiciones"), t("Operaciones"), t("Estrategias"), t("Avisos"),
                               t("Decisiones"), t("Registro"), t("Servidor")]):
            b = QPushButton(n); b.setProperty("rol", "nav"); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self.ir_a(i)); grupo.addButton(b); v.addWidget(b); self.nav.append(b)
        v.addStretch()
        st = QHBoxLayout(); st.setSpacing(8)
        self.punto = lbl(); self.punto.setFixedSize(10, 10); st.addWidget(self.punto)
        self.lbl_estado = lbl("", size=13, weight=600); st.addWidget(self.lbl_estado, 1); v.addLayout(st)
        self.lbl_estado_sub = lbl(t("Conectando con el servidor…"), rol="muted", size=12, wrap=True)
        v.addWidget(self.lbl_estado_sub); v.addSpacing(10)
        self.btn_revisar = boton(t("Revisar ahora"), accion=lambda: self._accion("revisar", t(
            "Listo: el bot revisa ahora (solo opera si hay velas nuevas cerradas).")))
        self.btn_bot = boton("", accion=self._alternar_bot)
        v.addWidget(self.btn_revisar); v.addWidget(self.btn_bot)
        return w

    def ir_a(self, i):
        self.nav[i].setChecked(True); self.paginas.setCurrentIndex(i); self.pintado = -1

    def _pagina(self, titulo, sub=None):
        w = QWidget(); w.setObjectName("pagina")
        v = QVBoxLayout(w); v.setContentsMargins(28, 24, 28, 24); v.setSpacing(16)
        v.addWidget(lbl(titulo, rol="h1"))
        if sub:
            v.addWidget(lbl(sub, rol="muted", size=13, wrap=True))
        return w, v

    # ---------- páginas
    def _pag_resumen(self):
        w, v = self._pagina(t("Resumen"), t("El bot corriendo en el servidor: cuánto tiene, cómo viene y lo último que hizo."))
        inner = QWidget(); iv = QVBoxLayout(inner); iv.setContentsMargins(0, 0, 0, 0); iv.setSpacing(16)
        self.banner = lbl("", size=13, wrap=True); self.banner.setVisible(False); iv.addWidget(self.banner)
        hero = panel(); hv = QHBoxLayout(hero); hv.setContentsMargins(20, 16, 24, 16); hv.setSpacing(28)
        sv = QVBoxLayout(); sv.setSpacing(4)
        sv.addWidget(lbl(t("Saldo del bot"), rol="muted", size=12))
        self.lbl_saldo = lbl("—", size=34, weight=600, family=FONT); sv.addWidget(self.lbl_saldo)
        self.lbl_rend = lbl("", size=13); sv.addWidget(self.lbl_rend)
        hv.addLayout(sv, 2)
        g = QGridLayout(); g.setHorizontalSpacing(24); self.kpi = {}
        for c, (k, tit) in enumerate([("cerrado", t("Resultado cerrado")), ("abierto", t("Resultado abierto")),
                                      ("libre", t("Sin asignar")), ("ops", t("Operaciones cerradas"))]):
            g.addWidget(lbl(tit, rol="muted", size=12), 0, c)
            x = lbl("—", size=16, weight=600); g.addWidget(x, 1, c); self.kpi[k] = x
        hv.addLayout(g, 3)
        self.btn_reanudar = boton(t("Reanudar"), "primario", self._reanudar); self.btn_reanudar.setVisible(False)
        hv.addWidget(self.btn_reanudar)
        mk = QVBoxLayout(); mk.setSpacing(8)
        mk.addWidget(lbl(t("Mercado ahora"), rol="muted", size=13))
        self.lbl_precios = {}
        for a in K.SYMBOLS:
            row = QHBoxLayout(); row.setSpacing(10)
            row.addWidget(lbl(a, size=14, weight=600)); row.addStretch()
            pl, cl = lbl("—", size=14, family=FONT), lbl("", size=12)
            cl.setMinimumWidth(96); cl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(pl); row.addWidget(cl)
            self.lbl_precios[a] = (pl, cl); mk.addLayout(row)
        self.lbl_precios_upd = lbl("", rol="muted", size=11, wrap=True); mk.addWidget(self.lbl_precios_upd)
        mkw = QWidget(); mkw.setLayout(mk); mkw.setFixedWidth(270); hv.addWidget(mkw)
        iv.addWidget(hero)
        pg = panel(); gv = QVBoxLayout(pg); gv.setContentsMargins(18, 14, 18, 14)
        gv.addWidget(lbl(t("Evolución del saldo"), rol="titulo"))
        self.grafico = GraficoCapital(); gv.addWidget(self.grafico, 1); iv.addWidget(pg)
        fila = QHBoxLayout(); fila.setSpacing(16)
        pa = panel(); pav = QVBoxLayout(pa); pav.setContentsMargins(18, 14, 18, 14)
        pav.addWidget(lbl(t("Posiciones abiertas"), rol="titulo"))
        self.lbl_abiertas = lbl("", size=13, wrap=True); pav.addWidget(self.lbl_abiertas); pav.addStretch()
        pm = panel(); pmv = QVBoxLayout(pm); pmv.setContentsMargins(18, 14, 18, 14)
        pmv.addWidget(lbl(t("Resultados por mes"), rol="titulo"))
        pmv.addWidget(lbl(t("El bot contra la simulación de Breakout y Resorte de tendencia en el mismo mes."),
                          rol="muted", size=12, wrap=True))
        self.tab_mes = tabla([t("Mes"), t("Saldo al cierre"), t("Bot"), t("Simulación"), t("Caída máxima")])
        self.tab_mes.setMinimumHeight(170); pmv.addWidget(self.tab_mes)
        fila.addWidget(pa, 2); fila.addWidget(pm, 3); iv.addLayout(fila)
        iv.addStretch(); v.addWidget(scroll(inner), 1)
        return w

    def _pag_posiciones(self):
        w, v = self._pagina(t("Posiciones"), t("Cada estrategia en cada moneda: cuánto tiene y si tiene una posición abierta."))
        self.tab_pos = tabla([t("Moneda"), t("Estrategia"), t("Monto"), t("Capital"), t("Posición"), t("Entrada"),
                              t("Stop"), t("Resultado")])
        v.addWidget(self.tab_pos, 1)
        return w

    def _pag_operaciones(self):
        w, v = self._pagina(t("Operaciones"), t("Todas las operaciones cerradas en este modo, la más reciente arriba."))
        self.lbl_ops = lbl("", size=13, wrap=True); v.addWidget(self.lbl_ops)
        self.tab_ops = tabla([t("Cierre"), t("Moneda"), t("Estrategia"), t("Lado"), t("Entrada"), t("Salida"),
                              t("Resultado"), t("Motivo")])
        v.addWidget(self.tab_ops, 1)
        return w

    def _pag_estrategias(self):
        w, v = self._pagina(t("Estrategias"), t("El piloto automático y cómo le fue a cada estrategia desde 2022."))
        inner = QWidget(); iv = QVBoxLayout(inner); iv.setContentsMargins(0, 0, 0, 0); iv.setSpacing(16)
        pa = panel(); pav = QVBoxLayout(pa); pav.setContentsMargins(18, 14, 18, 14); pav.setSpacing(8)
        ha = QHBoxLayout(); ha.addWidget(lbl(t("Piloto automático"), rol="titulo")); ha.addStretch()
        self.sw_piloto = QCheckBox(t("Piloto encendido")); self.sw_piloto.setProperty("rol", "switch")
        self.sw_piloto.setCursor(Qt.PointingHandCursor); self.sw_piloto.clicked.connect(self._cambiar_piloto)
        ha.addWidget(self.sw_piloto); pav.addLayout(ha)
        pav.addWidget(lbl(t("Con el piloto encendido el bot usa Breakout y Resorte de tendencia en BTC, ETH y SOL, reparte "
                            "todo el capital en partes iguales una vez por día y revisa una vez por mes que cada una siga "
                            "ganando. Si el laboratorio encuentra una que les gana durante 3 meses de observación, la suma."),
                          rol="muted", size=12, wrap=True))
        self.lbl_piloto = lbl("", size=13, wrap=True); pav.addWidget(self.lbl_piloto)
        self.lbl_cap_min = lbl("", size=13, wrap=True); pav.addWidget(self.lbl_cap_min)
        iv.addWidget(pa)
        iv.addWidget(lbl(t("Estrategias"), rol="titulo"))
        iv.addWidget(lbl(t("Resultado de cada año y de los últimos 4 semestres con la estrategia siempre prendida, en "
                           "promedio de BTC, ETH y SOL."), rol="muted", size=12, wrap=True))
        self.box_estr = QVBoxLayout(); self.box_estr.setSpacing(10); iv.addLayout(self.box_estr)
        self._estr_firma = None
        iv.addStretch(); v.addWidget(scroll(inner), 1)
        return w

    def _pag_avisos(self):
        w, v = self._pagina(t("Avisos"), t("Lo que el bot te avisó: revisión mensual del piloto, laboratorio, etc."))
        h = QHBoxLayout(); h.addStretch()
        h.addWidget(boton(t("Marcar todos como leídos"), accion=lambda: self._accion("avisos_leidos")))
        v.addLayout(h)
        inner = QWidget(); self.box_av = QVBoxLayout(inner); self.box_av.setContentsMargins(0, 0, 0, 0)
        self.box_av.setSpacing(10); self._av_firma = None
        v.addWidget(scroll(inner), 1)
        return w

    def _pag_decisiones(self):
        w, v = self._pagina(t("Decisiones"), t("Qué miró el bot en cada revisión, para cada estrategia en cada moneda: "
                                               "qué condiciones se cumplen (✓) y cuáles faltan (✗) para abrir."))
        h = QHBoxLayout(); h.addWidget(lbl(t("Revisión"), size=13))
        self.cmb_rev = QComboBox(); self.cmb_rev.setMinimumWidth(260)
        self.cmb_rev.currentIndexChanged.connect(lambda _i: self._pintar_decision())
        h.addWidget(self.cmb_rev); h.addStretch(); v.addLayout(h)
        inner = QWidget(); self.box_dec = QVBoxLayout(inner); self.box_dec.setContentsMargins(0, 0, 0, 0)
        self.box_dec.setSpacing(8); v.addWidget(scroll(inner), 1)
        self._dec_firma, self._dec = None, []
        return w

    def _p_decisiones(self, d):
        dec = (self.detalles.get("decisiones") or {}).get("decisiones")
        if dec is None:
            if self._dec_firma is None:
                self._vaciar_dec(); self.box_dec.addWidget(lbl(t("Cargando…"), rol="muted", size=13))
                self._dec_firma = "cargando"
            return
        firma = (len(dec), dec[0]["hora"] if dec else None)
        if firma == self._dec_firma:
            return
        en_ultima = self.cmb_rev.currentIndex() <= 0
        sel = self.cmb_rev.currentText()
        self._dec_firma, self._dec = firma, dec
        self.cmb_rev.blockSignals(True); self.cmb_rev.clear()
        for x in dec:
            h = datetime.fromisoformat(x["hora"])
            self.cmb_rev.addItem(t("{h}, vela de {v}", h=f"{h:%d/%m %H:%M}", v=x["vela"]))
        self.cmb_rev.setCurrentIndex(0 if en_ultima else max(0, self.cmb_rev.findText(sel)))
        self.cmb_rev.blockSignals(False)
        self._pintar_decision()

    def _vaciar_dec(self):
        while self.box_dec.count():
            it = self.box_dec.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _pintar_decision(self):
        self._vaciar_dec()
        if not self._dec:
            self.box_dec.addWidget(lbl(t("Todavía no hay revisiones registradas con el detalle de cada decisión. La "
                                         "primera aparece después de la próxima revisión del bot."), rol="muted", size=14,
                                       wrap=True))
            self.box_dec.addStretch(); return
        x = self._dec[max(0, self.cmb_rev.currentIndex())]
        ab = sum(1 for it in x["items"] if it["accion"] == "abre")
        ce = sum(1 for it in x["items"] if it["accion"] == "cierra")
        self.box_dec.addWidget(lbl(t("En esta revisión el bot abrió {a} y cerró {c} posiciones. Revisó {n} partes del "
                                     "capital.", a=ab, c=ce, n=len(x["items"])), size=14, wrap=True))
        acciones = {"abre": (t("Abre"), GAIN), "cierra": (t("Cierra"), ACCENT), "mantiene": (t("Mantiene"), AMBER),
                    "no_abre": (t("No abre"), MUTED), "inactiva": (t("Desactivada"), MUTED)}
        for it in x["items"]:
            card = panel(); hl = QHBoxLayout(card); hl.setContentsMargins(16, 12, 16, 12); hl.setSpacing(18)
            izq = QVBoxLayout(); izq.setSpacing(4)
            izq.addWidget(lbl(it["activo"], size=15, weight=600))
            izq.addWidget(lbl(it.get("estrategia", ""), rol="muted", size=12, wrap=True))
            txt, col = acciones.get(it["accion"], (it["accion"], MUTED))
            c = lbl("", rol="chip"); chip(c, txt, col); izq.addWidget(c, 0, Qt.AlignLeft); izq.addStretch()
            iz = QWidget(); iz.setLayout(izq); iz.setFixedWidth(180); hl.addWidget(iz)
            der = QVBoxLayout(); der.setSpacing(3)
            conds = it.get("condiciones") or []
            if it["accion"] == "no_abre" and conds:
                principal = t("Se cumplen {c} de {n} condiciones para entrar:", c=sum(1 for _, ok in conds if ok),
                              n=len(conds))
            elif it["accion"] == "no_abre":
                principal = t("No hubo señal de entrada.")
            else:
                tx = it.get("texto") or ""
                principal = (tx[0].upper() + tx[1:] + ".") if tx else ""
            der.addWidget(lbl(principal, size=13, wrap=True))
            for ctext, ok in conds:
                der.addWidget(lbl(("✓  " if ok else "✗  ") + ctext, size=12, color=GAIN if ok else LOSS, wrap=True))
            hl.addLayout(der, 1)
            self.box_dec.addWidget(card)
        self.box_dec.addStretch()

    def _pag_registro(self):
        w, v = self._pagina(t("Registro"), t("Lo que va haciendo el bot en el servidor, revisión por revisión."))
        self.txt_reg = QPlainTextEdit(); self.txt_reg.setReadOnly(True)
        f = QFont("Cascadia Mono"); f.setPixelSize(12); self.txt_reg.setFont(f)
        v.addWidget(self.txt_reg, 1)
        return w

    def _pag_servidor(self):
        w, v = self._pagina(t("Servidor"), t("Conexión, riesgo, capital, laboratorio y actualizaciones del bot en la nube. "
                                             "Las claves de Binance y el modo se cambian en el servidor, por seguridad."))
        inner = QWidget(); iv = QVBoxLayout(inner); iv.setContentsMargins(0, 0, 0, 0); iv.setSpacing(16)

        def seccion(titulo, ayuda=None):
            p = panel(); pv = QVBoxLayout(p); pv.setContentsMargins(18, 14, 18, 14); pv.setSpacing(8)
            pv.addWidget(lbl(titulo, rol="titulo"))
            if ayuda:
                pv.addWidget(lbl(ayuda, rol="muted", size=12, wrap=True))
            iv.addWidget(p)
            return pv
        pv = seccion(t("Conexión"))
        self.lbl_con = lbl("", size=13, wrap=True); pv.addWidget(self.lbl_con)
        h = QHBoxLayout(); h.addWidget(boton(t("Cambiar código de conexión"), accion=self._cambiar_codigo)); h.addStretch()
        pv.addLayout(h)

        pv = seccion(t("Riesgo"), t("Riesgo por operación, límite de pérdida (frena el bot si la cuenta pierde ese porcentaje "
                                    "del capital del modo) y espera de la orden límite antes de completarla a mercado."))
        g = QGridLayout(); g.setHorizontalSpacing(14)
        self.sp_riesgo = QDoubleSpinBox(); self.sp_riesgo.setRange(0.5, 10); self.sp_riesgo.setDecimals(1)
        self.sp_riesgo.setSingleStep(0.5); self.sp_riesgo.setSuffix(NB + "%")
        self.sp_limite = QSpinBox(); self.sp_limite.setRange(5, 90); self.sp_limite.setSuffix(NB + "%")
        self.sp_espera = QSpinBox(); self.sp_espera.setRange(10, 900); self.sp_espera.setSuffix(NB + "s")
        for r, (tit, sp) in enumerate([(t("Riesgo por operación"), self.sp_riesgo), (t("Límite de pérdida"), self.sp_limite),
                                       (t("Espera de la orden límite"), self.sp_espera)]):
            g.addWidget(lbl(tit, size=13), r, 0); g.addWidget(con_pasos(sp), r, 1)
        g.setColumnStretch(2, 1); pv.addLayout(g)
        h = QHBoxLayout(); h.addWidget(boton(t("Guardar riesgo"), "primario", self._guardar_riesgo)); h.addStretch()
        pv.addLayout(h); self._riesgo_cargado = False

        pv = seccion(t("Capital del modo"), t("Cuánto dinero de la cuenta usa el bot en el modo actual. Con el piloto "
                                              "encendido, el bot reparte el cambio solo."))
        h = QHBoxLayout()
        self.sp_capital = QDoubleSpinBox(); self.sp_capital.setRange(10, 1_000_000); self.sp_capital.setDecimals(2)
        self.sp_capital.setSingleStep(10); self.sp_capital.setSuffix(NB + "USDT"); self.sp_capital.setMinimumWidth(150)
        h.addWidget(con_pasos(self.sp_capital)); h.addWidget(boton(t("Guardar capital"), "primario", self._guardar_capital))
        h.addStretch(); pv.addLayout(h); self._capital_cargado = False
        self.lbl_cap_min_cfg = lbl("", size=13, wrap=True); pv.addWidget(self.lbl_cap_min_cfg)

        pv = seccion(t("Laboratorio de estrategias"), t(
            "Busca estrategias nuevas una vez por semana. La que aprueba el examen final queda 3 meses en observación "
            "sin dinero; si les gana a Breakout y Resorte, entra sola al piloto."))
        h = QHBoxLayout()
        self.sw_lab = QCheckBox(t("Activo")); self.sw_lab.setProperty("rol", "switch"); self.sw_lab.setCursor(Qt.PointingHandCursor)
        self.sw_lab.clicked.connect(lambda c: self._accion("laboratorio", activo=bool(c)))
        h.addWidget(self.sw_lab); h.addStretch()
        h.addWidget(boton(t("Buscar ahora"), accion=lambda: self._accion("buscar_estrategias", t(
            "Búsqueda iniciada: tarda unos 30 minutos."))))
        pv.addLayout(h)
        self.lbl_lab = lbl("", size=13, wrap=True); pv.addWidget(self.lbl_lab)
        self.box_cand = QVBoxLayout(); self.box_cand.setSpacing(8); pv.addLayout(self.box_cand); self._cand_firma = None

        pv = seccion(t("Actualizaciones del servidor"), t("El servidor busca versiones nuevas cada hora."))
        self.lbl_act = lbl("", size=13, wrap=True); pv.addWidget(self.lbl_act)
        h = QHBoxLayout()
        self.sw_act = QCheckBox(t("Instalar solas")); self.sw_act.setProperty("rol", "switch")
        self.sw_act.clicked.connect(lambda c: self._accion("actualizaciones_auto", activo=bool(c)))
        h.addWidget(self.sw_act); h.addStretch()
        h.addWidget(boton(t("Buscar ahora"), accion=lambda: self._accion("buscar_actualizacion")))
        h.addWidget(boton(t("Instalar"), "primario", lambda: self._accion("instalar_actualizacion", t(
            "Si había una versión nueva, se instaló y el servidor se reinicia (tarda menos de un minuto)."))))
        pv.addLayout(h)
        iv.addStretch(); v.addWidget(scroll(inner), 1)
        return w

    # ---------- acciones
    def _alternar_bot(self):
        d = self.datos or {}
        if (d.get("bot") or {}).get("corriendo"):
            if preguntar(self, t("Detener bot"), t("¿Detener el bot del servidor? Mientras esté detenido no abre ni cierra "
                                                   "operaciones (las abiertas quedan con su stop en Binance)."),
                         t("Detener"), t("Cancelar")):
                self._accion("detener")
        else:
            self._accion("iniciar")

    def _reanudar(self):
        if preguntar(self, t("Reanudar"), t("¿Permitir que el bot vuelva a abrir operaciones? El límite de pérdida se vuelve "
                                            "a medir desde el saldo actual."), t("Reanudar"), t("Cancelar")):
            self._accion("reanudar")

    def _cambiar_piloto(self, activo):
        texto = (t("¿Encender el piloto automático?") if activo else t("¿Apagar el piloto automático? El bot vuelve a usar "
                                                                         "las estrategias y montos que tenía a mano."))
        if preguntar(self, t("Piloto automático"), texto, t("Sí"), t("Cancelar")):
            self._accion("piloto", activo=bool(activo))
        self.pintado = -1

    def _guardar_riesgo(self):
        r = self.sp_riesgo.value()
        if r > 3 + 1e-9 and not preguntar(self, t("Riesgo"), t("Vas a arriesgar {p} por operación, más que el 3 % probado. "
                                                                "¿Guardar igual?", p=pct(r, 1)), t("Guardar"), t("Cancelar")):
            return
        self._accion("riesgo", t("Riesgo guardado y aplicado en el servidor."), por_operacion=round(r / 100, 4),
                     limite_perdida=round(self.sp_limite.value() / 100, 4), espera_limite=int(self.sp_espera.value()))

    def _guardar_capital(self):
        self._accion("capital", t("Capital guardado."), valor=float(self.sp_capital.value()))

    def _cambiar_codigo(self):
        c = pedir_codigo(self)
        if c:
            self.cliente = C.Cliente(c); self.pintado = -1

    # ---------- pintar
    def _pintar(self):
        if self.reiniciar_pendiente:
            self.reiniciar_pendiente = False
            return self._reiniciar()
        if self.pintado == self.version_datos:
            return
        self.pintado = self.version_datos
        d = self.datos
        if self.error:
            self.punto.setStyleSheet(f"background:{LOSS}; border-radius:5px")
            self.lbl_estado.setText(t("Sin conexión"))
            self.lbl_estado_sub.setText(self.error + ("\n" + t("Datos de hace {s} s.", s=int(time.time() - d["hora"]))
                                                      if d else ""))
            if not d:
                return
        if not d:
            return
        bot, s = d["bot"], d["snap"]
        corriendo = bot.get("corriendo")
        if not self.error:
            col = LOSS if s.get("frenado") else (GAIN if corriendo else AMBER)
            self.punto.setStyleSheet(f"background:{col}; border-radius:5px")
            self.lbl_estado.setText(t("Frenado") if s.get("frenado") else (t("Corriendo") if corriendo else t("Detenido")))
            sub = []
            if bot.get("proxima_revision"):
                sub.append(t("Próxima revisión: {h}", h=f"{datetime.fromtimestamp(bot['proxima_revision']):%H:%M}"))
            if bot.get("ultimo_error"):
                sub.append(str(bot["ultimo_error"])[:160])
            self.lbl_estado_sub.setText("\n".join(sub) or t("En el servidor"))
        self.lbl_modo.setText(t("Control remoto · {m}", m=d.get("nombre_modo", "")))
        self.btn_bot.setText(t("Detener bot") if corriendo else t("Iniciar bot"))
        self.btn_bot.setProperty("rol", "peligro" if corriendo else "primario"); self.btn_bot.style().polish(self.btn_bot)
        self.btn_revisar.setEnabled(bool(corriendo))
        i = self.paginas.currentIndex()
        [self._p_resumen, self._p_posiciones, self._p_operaciones, self._p_estrategias, self._p_avisos,
         self._p_decisiones, self._p_registro, self._p_servidor][i](d)
        self.nav[4].setText(t("Avisos ({n})", n=d.get("sin_leer")) if d.get("sin_leer") else t("Avisos"))

    def _p_resumen(self, d):
        s = d["snap"]
        avisos = []
        if s.get("frenado"):
            avisos.append(t("El bot está frenado por el límite de pérdida: no abre operaciones nuevas hasta que lo reanudes."))
        if app_local_abierta():
            avisos.append(t("La app del bot también está abierta en esta PC. Si opera la misma cuenta de Binance que el "
                            "servidor, las órdenes se duplican: cerrala (Salir, desde el ícono junto a la hora) y "
                            "desactivá 'Abrir al iniciar Windows'."))
        self.banner.setText("\n\n".join(avisos)); self.banner.setVisible(bool(avisos))
        self.banner.setStyleSheet(f"font-size:13px; color:{TEXT}; border:1px solid {AMBER}; border-left:4px solid {AMBER}; "
                                  f"border-radius:8px; padding:10px 12px")
        self.btn_reanudar.setVisible(bool(s.get("frenado")))
        for a, (pl, cl) in self.lbl_precios.items():
            x = (s.get("precios") or {}).get(a)
            if x:
                pl.setText(U.A.fmt_precio(x["precio"]))
                ch = x.get("cambio")
                cl.setText(t("{v} en 24 h", v=pct(ch, 1, True)) if ch is not None else "")
                cl.setStyleSheet(f"font-size:12px; color:{color_de(ch)}")
        if d.get("precios_hora"):
            seg = max(0, int(time.time() - d["precios_hora"]))
            self.lbl_precios_upd.setText(t("Binance Futuros, hace {x}", x=f"{seg}{NB}s" if seg < 120 else U.A.fmt_dur(seg)))
        else:
            self.lbl_precios_upd.setText(t("No se pudieron leer los precios. Reintentando."))
        self.lbl_saldo.setText(usd(s["saldo"]))
        self.lbl_rend.setText(t("{p} sobre el capital de {c}", p=pct(s["rendimiento_pct"], 2, True), c=usd(s["base"])))
        self.lbl_rend.setStyleSheet(f"font-size:13px; color:{color_de(s['rendimiento_pct'])}")
        for k, v, c in (("cerrado", usd(s["realizado"], 2, True), color_de(s["realizado"])),
                        ("abierto", usd(s["abierto"], 2, True), color_de(s["abierto"])),
                        ("libre", usd(s["libre"]), TEXT), ("ops", str(s["resumen_ops"]["n"]), TEXT)):
            self.kpi[k].setText(v); self.kpi[k].setStyleSheet(f"font-size:16px; font-weight:600; color:{c}")
        cur = (self.detalles.get("curva") or {}).get("curva") or []
        self.grafico.set_puntos([tuple(p) for p in cur], s["base"])
        ab = s.get("abiertas") or []
        self.lbl_abiertas.setText("\n".join(
            f"{f['activo']} {f['estrategia']}: {t('compra') if f['lado'] == 'long' else t('venta')} · "
            f"{usd(f['pnl'], 2, True) if f.get('pnl') is not None else '—'}" for f in ab) or
            t("Sin posiciones abiertas. El bot entra cuando aparece una señal."))
        meses, _dd = s.get("mensual") or ([], 0)
        hist = (d.get("historial") or {}).get("estrategias") or {}
        base = [b for b in K.PILOTO_BASE if b in hist]
        hoy = datetime.now().strftime("%Y-%m")
        filas = list(reversed(meses))[:24]
        self.tab_mes.setRowCount(len(filas))
        for r, x in enumerate(filas):
            vals = [(hist[b].get("mensual") or {}).get(x["mes"]) for b in base]
            sim = sum(vals) / len(vals) if base and x["mes"] < hoy and all(v is not None for v in vals) else None
            celda(self.tab_mes, r, 0, f"{x['mes'][5:]}/{x['mes'][:4]}", bold=True)
            celda(self.tab_mes, r, 1, usd(x["fin"]))
            celda(self.tab_mes, r, 2, pct(x.get("pct"), 1, True) if x.get("pct") is not None else "—", color_de(x.get("pct")))
            celda(self.tab_mes, r, 3, pct(sim, 1, True) if sim is not None else "—", color_de(sim) if sim is not None else MUTED)
            celda(self.tab_mes, r, 4, pct(x["dd"], 1) if x.get("dd") else "—", MUTED)

    def _p_posiciones(self, d):
        filas = d["snap"]["posiciones"]
        tb = self.tab_pos; tb.setRowCount(len(filas))
        for r, f in enumerate(filas):
            celda(tb, r, 0, f["activo"], bold=True); celda(tb, r, 1, f["estrategia"])
            celda(tb, r, 2, usd(f["asignado"])); celda(tb, r, 3, usd(f["capital"]))
            celda(tb, r, 4, (t("Compra") if f["lado"] == "long" else t("Venta")) if f["lado"] else "—")
            celda(tb, r, 5, num(f["entrada"], 2) if f["entrada"] else "—")
            celda(tb, r, 6, num(f["stop"], 2) if f["stop"] else "—")
            celda(tb, r, 7, usd(f["pnl"], 2, True) if f.get("pnl") is not None else "—", color_de(f.get("pnl")))

    def _p_operaciones(self, d):
        ops = (self.detalles.get("operaciones") or {}).get("operaciones") or []  # la más reciente primero
        r_ = d["snap"]["resumen_ops"]
        self.lbl_ops.setText(t("{n} operaciones, {g} ganadoras ({p}). Resultado: {r}.", n=r_["n"], g=r_["ganadas"],
                               p=pct(r_["pct"], 0) if r_["pct"] is not None else "—", r=usd(r_["pnl"], 2, True)))
        tb = self.tab_ops; tb.setRowCount(len(ops))
        for r, o in enumerate(ops):
            celda(tb, r, 0, str(o.get("salida_t") or "")[:16]); celda(tb, r, 1, o.get("activo", ""))
            celda(tb, r, 2, o.get("estrategia", "")); celda(tb, r, 3, t("Compra") if o.get("lado") == "long" else t("Venta"))
            celda(tb, r, 4, num(o.get("entrada"), 2)); celda(tb, r, 5, num(o.get("salida"), 2))
            celda(tb, r, 6, usd(o.get("pnl"), 2, True), color_de(o.get("pnl"))); celda(tb, r, 7, str(o.get("motivo", "")))

    def _minimo_parte(self, d, s_, a):
        """Lo que pide hoy Binance para que la orden de una parte llegue al mínimo (misma cuenta que la app de PC)."""
        from engine import STRATS
        mn, an = (d["mercado"].get("minimos") or {}).get(a), (d["mercado"].get("analisis") or {}).get(a)
        if not mn or not an or not an.get("atr_pct") or s_ not in STRATS or d["modo"] == "simulado":
            return None
        return mn * STRATS[s_]["stop_atr"] * an["atr_pct"] / d["riesgo"]["por_operacion"]

    def _texto_cap_min(self, d):
        s, au = d["snap"], d["snap"].get("auto_estado") or {}
        estr = (au.get("dentro") if au.get("dentro") is not None else d.get("piloto_base")) if s.get("auto") else s.get("activas")
        partes = [(x, a) for x in (estr or []) for a in K.SYMBOLS]
        mins = {p: self._minimo_parte(d, *p) for p in partes}
        if not partes or any(not v for v in mins.values()):
            return None
        (smax, amax), mmax = max(mins.items(), key=lambda x: x[1])
        por_parte = mmax * 1.25; total = por_parte * len(partes)
        disp = s["saldo_cerrado"]
        txt = (t("Capital mínimo recomendado: {t} en total", t=usd(total, 0)) + "\n" +
               t("Son {n} partes de {p} cada una (lo que más pide hoy Binance es {e} en {a}, más un 25 % de margen).",
                 n=len(partes), p=usd(por_parte, 0), e=d["nombres"].get(smax, smax), a=amax) + "\n" +
               (t("El bot tiene {d}: alcanza.", d=usd(disp, 0)) if disp >= total else
                t("El bot tiene {d}: no alcanza para todas las partes.", d=usd(disp, 0))))
        return txt, (GAIN if disp >= total else AMBER)

    def _caja(self, etiqueta, contenido):
        if not contenido:
            etiqueta.setVisible(False); return
        txt, col = contenido
        etiqueta.setText(txt); etiqueta.setVisible(True)
        etiqueta.setStyleSheet(f"font-size:13px; color:{TEXT}; border:1px solid {col}; border-left:4px solid {col}; "
                               f"border-radius:8px; padding:10px 12px")

    def _p_estrategias(self, d):
        s = d["snap"]; au = s.get("auto_estado") or {}
        self.sw_piloto.blockSignals(True); self.sw_piloto.setChecked(bool(s.get("auto"))); self.sw_piloto.blockSignals(False)
        self.sw_piloto.setText(t("Piloto encendido") if s.get("auto") else t("Piloto apagado"))
        if s.get("auto"):
            asig = au.get("asig") or {}
            dentro = au.get("dentro") or d.get("piloto_base") or []
            lineas = [t("En uso: {e}.", e=", ".join(d["nombres"].get(x, x) for x in dentro) or t("ninguna"))]
            if asig:
                lineas.append(t("{n} partes de {m} cada una.", n=len(asig), m=usd(next(iter(asig.values())))))
            for x in dentro:
                r = (au.get("revision") or {}).get(x) or {}
                sem = r.get("semestres") or []
                ua = M.ultimo_anio(sem)
                if ua is not None:
                    lineas.append(t("{e}: últimos 12 meses {p}; fallas seguidas {r} de {n}.", e=d["nombres"].get(x, x),
                                    p=pct(ua, 1, True), r=(au.get("racha") or {}).get(x, 0), n=d.get("meses_histeresis", 3)))
            self.lbl_piloto.setText("\n".join(lineas))
        else:
            self.lbl_piloto.setText(t("Piloto apagado: el bot usa las estrategias y montos elegidos a mano."))
        self._caja(self.lbl_cap_min, self._texto_cap_min(d))
        hist = (d.get("historial") or {}).get("estrategias") or {}
        firma = (tuple(sorted(hist)), (d.get("historial") or {}).get("calculado"))
        if firma == self._estr_firma:
            return
        self._estr_firma = firma
        while self.box_estr.count():
            it = self.box_estr.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        anios = [str(y) for y in range(2022, datetime.now().year + 1)]
        for k, x in hist.items():
            if k in d.get("retiradas", []):
                continue
            p = panel(); pv = QVBoxLayout(p); pv.setContentsMargins(18, 12, 18, 12); pv.setSpacing(6)
            top = QHBoxLayout(); top.addWidget(lbl(d["nombres"].get(k, k), rol="titulo"))
            ch = lbl("", rol="chip")
            chip(ch, t("Base del piloto") if k in K.PILOTO_BASE else (t("En el piloto (del laboratorio)") if k in
                                                                     d.get("piloto_base", []) else t("Del laboratorio")),
                 ACCENT if k in d.get("piloto_base", []) else AMBER)
            top.addWidget(ch); top.addStretch(); pv.addLayout(top)
            ok, sem = M.califica({"estrategias": {k: x}}, k)
            ua = M.ultimo_anio(sem)
            pv.addWidget(lbl(t("Historial insuficiente para la revisión mensual.") if ok is None else
                             (t("Ganó {p} en los últimos 12 meses: pasa la revisión.", p=pct(ua, 1, True)) if ok else
                              t("Perdió {p} en los últimos 12 meses: no pasa la revisión.", p=pct(ua, 1, True))),
                             size=13, color=MUTED if ok is None else (GAIN if ok else LOSS)))
            g = QGridLayout(); g.setHorizontalSpacing(22)
            for c, y in enumerate(anios):
                g.addWidget(lbl(y, rol="muted", size=12), 0, c)
                v = (x.get("anios") or {}).get(y)
                g.addWidget(lbl(pct(v, 0, True) if v is not None else "—", size=13, color=color_de(v) if v is not None else MUTED), 1, c)
            g.addWidget(lbl(t("Últimos 4 semestres"), rol="muted", size=12), 0, len(anios))
            g.addWidget(lbl("  ·  ".join(pct(v, 0, True) for v in sem) or "—", size=13), 1, len(anios))
            g.setColumnStretch(len(anios) + 1, 1); pv.addLayout(g)
            self.box_estr.addWidget(p)

    def _p_avisos(self, d):
        firma = tuple((a["id"], a.get("leida")) for a in d.get("alertas", []))
        if firma == self._av_firma:
            return
        self._av_firma = firma
        while self.box_av.count():
            it = self.box_av.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not d.get("alertas"):
            self.box_av.addWidget(lbl(t("No hay avisos."), rol="muted", size=13))
        for a in d.get("alertas", []):
            p = panel(); pv = QVBoxLayout(p); pv.setContentsMargins(16, 10, 16, 10); pv.setSpacing(4)
            h = QHBoxLayout(); h.addWidget(lbl(a["titulo"], size=14, weight=600 if not a.get("leida") else 400))
            h.addStretch(); h.addWidget(lbl(f"{datetime.fromtimestamp(a['hora']):%d/%m %H:%M}", rol="muted", size=12))
            pv.addLayout(h); pv.addWidget(lbl(a.get("texto", ""), size=13, wrap=True))
            self.box_av.addWidget(p)
        self.box_av.addStretch()

    def _p_registro(self, d):
        lineas = (self.detalles.get("registro") or {}).get("lineas")
        if lineas is None:
            self.txt_reg.setPlainText(t("Cargando…")); return
        sb = self.txt_reg.verticalScrollBar(); abajo = sb.value() >= sb.maximum() - 4
        self.txt_reg.setPlainText("\n".join(lineas))
        if abajo:
            sb.setValue(sb.maximum())

    def _p_servidor(self, d):
        self.lbl_con.setText(t("Conectado a {h}:{p}. Servidor versión {v}, modo {m}. Claves cargadas: demo {cd}, real {cr}.",
                               h=self.cliente.host, p=self.cliente.puerto, v=d["version"], m=d["nombre_modo"],
                               cd=t("sí") if d["claves"].get("demo") else t("no"),
                               cr=t("sí") if d["claves"].get("real") else t("no")))
        r = d["riesgo"]
        if not self._riesgo_cargado:
            self.sp_riesgo.setValue(r["por_operacion"] * 100); self.sp_limite.setValue(int(round(r["limite_perdida"] * 100)))
            self.sp_espera.setValue(int(r.get("espera_limite") or 180)); self._riesgo_cargado = True
        if not self._capital_cargado:
            self.sp_capital.setValue(float((d.get("capital") or {}).get(d["modo"], 100))); self._capital_cargado = True
        self._caja(self.lbl_cap_min_cfg, self._texto_cap_min(d))
        lab = d["laboratorio"]
        self.sw_lab.blockSignals(True); self.sw_lab.setChecked(bool((lab.get("ajustes") or {}).get("activo")))
        self.sw_lab.blockSignals(False)
        est = lab.get("estado") or {}
        if lab.get("corriendo"):
            self.lbl_lab.setText(t("Buscando ahora: {m}", m=est.get("mensaje", "")))
        elif est.get("fin"):
            self.lbl_lab.setText(t("Última búsqueda: {f}. Probó {n} combinaciones.", f=f"{datetime.fromtimestamp(est['fin']):%d/%m %H:%M}",
                                   n=est.get("probadas", 0)))
        else:
            self.lbl_lab.setText(t("Todavía no buscó."))
        firma = tuple((c["id"], (c.get("observacion") or {}).get("actualizado")) for c in lab.get("candidatas", []))
        if firma != self._cand_firma:
            self._cand_firma = firma
            while self.box_cand.count():
                it = self.box_cand.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
            for c in lab.get("candidatas", []):
                ob = c.get("observacion") or {}
                fila = QWidget(); h = QHBoxLayout(fila); h.setContentsMargins(0, 0, 0, 0)
                txt = c.get("nombre", c["id"]) + " — " + (
                    t("en observación: ella {a}, Breakout y Resorte {b}.", a=pct(ob["ella"], 1, True), b=pct(ob["base"], 1, True))
                    if ob.get("ella") is not None else t("en observación (todavía sin resultado)."))
                h.addWidget(lbl(txt, size=13, wrap=True), 1)
                h.addWidget(boton(t("Dejar de observarla"), accion=lambda _=False, i=c["id"]: self._accion("descartar_candidata", id=i)))
                self.box_cand.addWidget(fila)
        a = d.get("actualizacion") or {}
        self.sw_act.blockSignals(True); self.sw_act.setChecked(bool(d.get("actualizaciones_auto", True)))
        self.sw_act.blockSignals(False)
        self.lbl_act.setText({"al día": t("Al día (versión {v}).", v=d["version"]),
                              "disponible": t("Hay una versión nueva: {v}.", v=a.get("version")),
                              "instalada": t("Versión {v} instalada; el servidor se está reiniciando.", v=a.get("version")),
                              "error": t("No se pudo buscar: {e}", e=a.get("detalle", ""))}.get(a.get("estado"),
                                                                                                t("Todavía no buscó.")))


def main():
    app = QApplication(sys.argv)
    app._sin_rueda = SinRueda(app); app.installEventFilter(app._sin_rueda)
    try:
        app.setStyleSheet(QSS + qss_flechas())
    except Exception:
        app.setStyleSheet(QSS)
    f = QFont(FONT_TXT); f.setPixelSize(13); app.setFont(f)
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        try:
            limpiar_app_vieja()
        except Exception as e:
            print("limpieza:", type(e).__name__, e)
    codigo = leer_codigo() or pedir_codigo(None)
    if not codigo:
        return
    w = Control(codigo); w.show()
    code = app.exec()
    w.parar.set()
    sys.exit(code)


if __name__ == "__main__":
    main()
