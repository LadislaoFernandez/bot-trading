"""Ventanas de la app de Windows para dejar el bot funcionando sin comandos:

- AsistenteServidor: crea el servidor en Oracle Cloud con la API de Oracle (oci_api.py), espera a que el bot responda
  y guarda el código de conexión.
- DialogoClaves: conecta Binance (demo o real). El servidor genera la clave Ed25519 y nunca la entrega; la app solo
  le pasa la API key que muestra Binance.
"""
import os
import threading
import time
import webbrowser

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLineEdit, QPlainTextEdit, QStackedWidget, QVBoxLayout,
                               QWidget)

import cliente_api as C
import oci_api as O
from app import aviso, boton, lbl, preguntar
from i18n import t

URL_ORACLE_ALTA = "https://www.oracle.com/cloud/free/"
URL_BINANCE_API = {"demo": "https://demo.binance.com/es/my/settings/api-management",
                   "real": "https://www.binance.com/es/my/settings/api-management"}
ARCH_CLAVE_OCI = "oracle_clave_api.dat"  # cifrada con la cuenta de Windows (como el código de conexión)


def _guardar_secreto(ruta, texto):
    import claves as CL
    CL._escribir(ruta, CL._proteger(texto.encode("utf-8")))


def _leer_secreto(ruta):
    import claves as CL
    try:
        with open(ruta, "rb") as f:
            return CL._desproteger(f.read()).decode("utf-8")
    except (OSError, ValueError):
        return None


def _texto_copiable(texto, alto=110):
    e = QPlainTextEdit(texto); e.setReadOnly(True); e.setFixedHeight(alto)
    return e


def _copiar(texto, boton_):
    QGuiApplication.clipboard().setText(texto)
    boton_.setText(t("Copiado"))
    QTimer.singleShot(2000, lambda: boton_.setText(t("Copiar")))


def _pagina(titulo, texto):
    w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(10)
    v.addWidget(lbl(titulo, size=20, weight=600))
    if texto:
        v.addWidget(lbl(texto, size=13, wrap=True))
    return w, v


# ------------------------------------------------------------------ crear el servidor en Oracle
class AsistenteServidor(QDialog):
    """Al terminar, self.codigo tiene el código de conexión del servidor nuevo (ya guardado)."""

    def __init__(self, parent=None, guardar_codigo=None):
        super().__init__(parent)
        self.setWindowTitle(t("Crear el servidor del bot"))
        self.resize(760, 640)
        self.guardar_codigo, self.codigo = guardar_codigo, None
        self.priv = _leer_secreto(ARCH_CLAVE_OCI)
        if self.priv:
            self.pub = None
        else:
            self.priv, self.pub, _ = O.generar_clave_api()
            _guardar_secreto(ARCH_CLAVE_OCI, self.priv)
        if self.pub is None:
            from cryptography.hazmat.primitives import serialization
            k = serialization.load_pem_private_key(self.priv.encode(), None)
            self.pub = k.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        v = QVBoxLayout(self); v.setContentsMargins(24, 20, 24, 20)
        self.pasos = QStackedWidget(); v.addWidget(self.pasos, 1)
        self.pasos.addWidget(self._p_inicio()); self.pasos.addWidget(self._p_clave())
        self.pasos.addWidget(self._p_progreso()); self.pasos.addWidget(self._p_listo())
        self._log, self._fin, self._error, self._mostrado = [], None, None, 0
        self.reloj = QTimer(self); self.reloj.timeout.connect(self._mirar); self.reloj.start(500)

    def _p_inicio(self):
        w, v = _pagina(t("Tu servidor gratis en Oracle Cloud"), t(
            "El bot corre en una máquina gratis de Oracle, así funciona las 24 horas aunque apagues la PC. La app la crea "
            "y la deja funcionando sola; vos solo necesitás una cuenta de Oracle Cloud."))
        v.addWidget(lbl(t(
            "1. Si no tenés cuenta, creala en oracle.com/cloud/free (\"Start for free\"). Oracle pide una tarjeta solo "
            "para verificar tu identidad: con los recursos Always Free no cobra nada.\n\n"
            "2. MUY IMPORTANTE: como región de inicio (Home Region) elegí Brazil East (Sao Paulo) o Chile Central "
            "(Santiago). Binance bloquea los servidores de Estados Unidos y la región no se puede cambiar después.\n\n"
            "3. Esperá el mail de que la cuenta está lista y entrá a cloud.oracle.com."), size=13, wrap=True))
        h = QHBoxLayout()
        h.addWidget(boton(t("Crear cuenta de Oracle"), accion=lambda: webbrowser.open(URL_ORACLE_ALTA)))
        h.addStretch()
        h.addWidget(boton(t("Ya tengo la cuenta: seguir"), "primario", lambda: self.pasos.setCurrentIndex(1)))
        v.addStretch(); v.addLayout(h)
        return w

    def _p_clave(self):
        w, v = _pagina(t("Darle permiso a la app"), t(
            "La app necesita una clave de API de Oracle para crear la máquina. La generó recién: agregá esta clave "
            "pública en tu perfil de Oracle y pegá acá el texto que Oracle te muestra."))
        v.addWidget(lbl(t(
            "1. En cloud.oracle.com tocá el ícono de tu perfil (arriba a la derecha) → \"My profile\" (Mi perfil) → "
            "pestaña o sección \"API keys\" → \"Add API key\".\n"
            "2. Elegí \"Paste a public key\" (Pegar una clave pública), pegá la clave de abajo y tocá \"Add\"."),
            size=13, wrap=True))
        h = QHBoxLayout(); h.addWidget(lbl(t("Clave pública"), size=13, weight=600)); h.addStretch()
        bc = boton(t("Copiar")); bc.clicked.connect(lambda: _copiar(self.pub, bc)); h.addWidget(bc)
        v.addLayout(h); v.addWidget(_texto_copiable(self.pub, 120))
        v.addWidget(lbl(t("3. Oracle muestra \"Configuration file preview\": copiá todo ese texto (empieza con "
                          "[DEFAULT]) y pegalo acá."), size=13, wrap=True))
        self.txt_cfg = QPlainTextEdit(); self.txt_cfg.setFixedHeight(130)
        self.txt_cfg.setPlaceholderText("[DEFAULT]\nuser=ocid1.user.oc1..\nfingerprint=…\ntenancy=ocid1.tenancy.oc1..\n"
                                        "region=sa-saopaulo-1")
        v.addWidget(self.txt_cfg)
        h = QHBoxLayout()
        h.addWidget(boton(t("Volver"), accion=lambda: self.pasos.setCurrentIndex(0))); h.addStretch()
        h.addWidget(boton(t("Crear el servidor"), "primario", self._crear))
        v.addStretch(); v.addLayout(h)
        return w

    def _p_progreso(self):
        w, v = _pagina(t("Creando tu servidor"), t(
            "Tarda unos 15 minutos: Oracle crea la máquina y después el bot se instala solo. Podés dejar esta ventana "
            "abierta y hacer otra cosa."))
        self.txt_log = QPlainTextEdit(); self.txt_log.setReadOnly(True); v.addWidget(self.txt_log, 1)
        self.btn_reintentar = boton(t("Volver a intentar"), "primario", lambda: self.pasos.setCurrentIndex(1))
        self.btn_reintentar.setVisible(False)
        h = QHBoxLayout(); h.addStretch(); h.addWidget(self.btn_reintentar); v.addLayout(h)
        return w

    def _p_listo(self):
        w, v = _pagina(t("¡Servidor listo!"), "")
        self.lbl_listo = lbl("", size=13, wrap=True); v.addWidget(self.lbl_listo)
        v.addStretch()
        h = QHBoxLayout(); h.addStretch(); h.addWidget(boton(t("Seguir: conectar Binance"), "primario", self.accept))
        v.addLayout(h)
        return w

    # ----- trabajo en segundo plano
    def log(self, x):
        self._log.append(f"{time.strftime('%H:%M:%S')}  {x}")

    def _crear(self):
        try:
            cfg = O.leer_configuracion(self.txt_cfg.toPlainText())
        except ValueError as e:
            return aviso(self, t("Clave de API"), str(e), True)
        if cfg["fingerprint"].lower() != O.huella_de_privada(self.priv):
            return aviso(self, t("Clave de API"), t(
                "La huella (fingerprint) del texto pegado no coincide con la clave de esta app. Revisá que hayas "
                "agregado la clave pública que muestra esta ventana."), True)
        if cfg["region"] not in O.REGIONES_OK:
            return aviso(self, t("Región"), t(
                "Tu cuenta de Oracle está en la región {r}. Hace falta una cuenta con región de inicio Sao Paulo o "
                "Santiago: Binance no funciona desde los servidores de Estados Unidos.", r=cfg["region"]), True)
        self._log, self._fin, self._error, self._mostrado = [], None, None, 0
        self.txt_log.clear(); self.btn_reintentar.setVisible(False)
        self.pasos.setCurrentIndex(2)
        threading.Thread(target=self._trabajo, args=(cfg,), daemon=True).start()

    def _trabajo(self, cfg):
        try:
            token = O.nuevo_token()
            cert, clave, huella = O.generar_certificado()
            ssh_priv, ssh_pub = O.generar_ssh()
            res = O.crear_servidor(O.OCI(cfg, self.priv), O.script_arranque(token, cert, clave), ssh_pub, log=self.log)
            ruta_ssh = os.path.join(os.path.expanduser("~"), ".ssh", f"bot-trading-{res['ip']}.key")
            try:
                os.makedirs(os.path.dirname(ruta_ssh), exist_ok=True)
                with open(ruta_ssh, "w", encoding="utf-8") as f:
                    f.write(ssh_priv)
            except OSError:
                ruta_ssh = None
            codigo = O.codigo_conexion(res["ip"], token, huella)
            self.log(t("Máquina lista en {ip}. Instalando el bot (unos 10 minutos)…", ip=res["ip"]))
            cli, fin = C.Cliente(codigo), time.time() + 30 * 60
            while True:
                try:
                    cli.estado(); break
                except (C.ErrorConexion, C.ErrorServidor):
                    if time.time() > fin:
                        raise RuntimeError(t("El servidor no respondió en 30 minutos. Puede que la instalación siga: "
                                             "abrí la app más tarde con este código: {c}", c=codigo))
                    time.sleep(20)
            if self.guardar_codigo:
                self.guardar_codigo(codigo)
            self.codigo = codigo
            self._fin = (res, ruta_ssh)
        except Exception as e:
            self._error = f"{type(e).__name__}: {e}"

    def _mirar(self):
        while self._mostrado < len(self._log):
            self.txt_log.appendPlainText(self._log[self._mostrado]); self._mostrado += 1
        if self._error:
            self.txt_log.appendPlainText("\n" + t("No se pudo terminar:") + " " + self._error)
            self._error = None; self.btn_reintentar.setVisible(True)
        if self._fin:
            res, ruta = self._fin; self._fin = None
            self.lbl_listo.setText(t(
                "El bot ya está corriendo en tu servidor de Oracle ({ip}, máquina {f}), en modo simulado: usa precios "
                "reales pero todavía no opera. La app quedó conectada.\n\nFalta conectar tu cuenta de Binance: es el "
                "paso siguiente.", ip=res["ip"], f=res["forma"]) + (
                "\n\n" + t("Por si alguna vez hace falta entrar al servidor, la llave SSH quedó en {r}.", r=ruta)
                if ruta else ""))
            self.pasos.setCurrentIndex(3)


# ------------------------------------------------------------------ conectar Binance (demo o real)
class DialogoClaves(QDialog):
    def __init__(self, parent, cliente, modo):
        super().__init__(parent)
        self.cliente, self.modo = cliente, modo
        self.setWindowTitle(t("Conectar Binance {m}", m="demo" if modo == "demo" else t("(dinero real)")))
        self.resize(720, 640)
        r = cliente.accion("claves_iniciar", modo=modo)
        self.pub, ip = r["publica"], r.get("ip") or "?"
        v = QVBoxLayout(self); v.setContentsMargins(24, 20, 24, 20); v.setSpacing(10)
        v.addWidget(lbl(t("Conectar tu cuenta de Binance"), size=20, weight=600))
        v.addWidget(lbl(t(
            "Tu servidor generó una clave para Binance. La parte privada nunca sale del servidor; a Binance solo le "
            "das la parte pública, y a la app solo la API key que te devuelve Binance."), size=13, wrap=True))
        v.addWidget(lbl(t(
            "1. Abrí la gestión de API de Binance{d} → \"Crear API\" → \"Generada por el usuario\" (Self-generated).\n"
            "2. Pegá esta clave pública completa (con las líneas BEGIN y END):",
            d=" demo" if modo == "demo" else ""), size=13, wrap=True))
        h = QHBoxLayout()
        h.addWidget(boton(t("Abrir Binance"), accion=lambda: webbrowser.open(URL_BINANCE_API[modo]))); h.addStretch()
        bc = boton(t("Copiar")); bc.clicked.connect(lambda: _copiar(self.pub, bc)); h.addWidget(bc)
        v.addLayout(h); v.addWidget(_texto_copiable(self.pub, 96))
        v.addWidget(lbl(t(
            "3. Ponele un nombre, confirmá y en los permisos activá solo \"Habilitar futuros\" (sin retiros).\n"
            "4. En \"Restringir el acceso a IP de confianza\" agregá la IP de tu servidor: {ip}\n"
            "5. Copiá la API Key que te muestra Binance y pegala acá:", ip=ip), size=13, wrap=True))
        self.e_key = QLineEdit(); self.e_key.setPlaceholderText("API Key"); v.addWidget(self.e_key)
        self.lbl_res = lbl("", size=13, wrap=True); v.addWidget(self.lbl_res)
        v.addStretch()
        h = QHBoxLayout(); h.addWidget(boton(t("Cancelar"), accion=self.reject)); h.addStretch()
        self.btn = boton(t("Probar y guardar"), "primario", self._probar); h.addWidget(self.btn)
        v.addLayout(h)

    def _probar(self):
        key = self.e_key.text().strip()
        if not key:
            return
        self.btn.setEnabled(False); self.lbl_res.setText(t("Probando la conexión con Binance…"))
        QTimer.singleShot(50, lambda: self._probar2(key))

    def _probar2(self, key):
        try:
            r = self.cliente.accion("claves_completar", modo=self.modo, api_key=key)
        except (C.ErrorConexion, C.ErrorServidor) as e:
            self.lbl_res.setText(t("No funcionó:") + f" {e}"); self.btn.setEnabled(True); return
        s = r.get("saldo") or {}
        txt = t("Conexión OK. Saldo en futuros: {s} USDT.", s=f"{s.get('total', 0):,.2f}")
        p = r.get("permisos")
        if p and (p.get("retiros") or not p.get("ip") or not p.get("futuros")):
            aviso(self, t("Permisos de la clave"), txt + "\n\n" + t(
                "Para dinero real la clave tiene que tener futuros habilitados, retiros deshabilitados y restricción de "
                "IP. Corregilo en Binance y volvé a probar."), True)
            self.btn.setEnabled(True); return
        if not preguntar(self, t("Binance conectado"), txt + "\n\n" + (
                t("¿Pasar el bot a modo demo ahora? Va a operar la cuenta demo de Binance.") if self.modo == "demo" else
                t("¿Pasar el bot a DINERO REAL ahora?")), t("Sí, cambiar"), t("Después")):
            return self.accept()
        datos = {"modo": self.modo}
        if self.modo == "real":
            from PySide6.QtWidgets import QInputDialog
            x, ok = QInputDialog.getText(self, t("Dinero real"), t(
                "Vas a operar con DINERO REAL y podés perder dinero. Revisá el capital del modo real en Servidor.\n\n"
                "Escribí REAL para confirmar:"))
            if not ok or x.strip() != "REAL":
                return self.accept()
            datos["confirmar"] = "REAL"
        try:
            self.cliente.accion("cambiar_modo", **datos)
            aviso(self, t("Modo cambiado"), t("Listo. El servidor se reinicia para aplicar el cambio (menos de un "
                                              "minuto)."))
        except (C.ErrorConexion, C.ErrorServidor) as e:
            aviso(self, t("Modo"), str(e), True)
        self.accept()
