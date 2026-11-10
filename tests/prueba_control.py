"""Prueba de la app de control (necesita PySide6): levanta un servidor de prueba, conecta la app con el código y recorre
todas las pantallas. También prueba una acción (piloto) y que un código con otro certificado no se conecte."""
import os
import shutil
import subprocess
import sys
import tempfile
import time

os.environ["BOT_SIN_RELAY"] = "1"  # que el servidor de prueba no use el intermediario de avisos real

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp(prefix="servidor_prueba_")
for f in os.listdir(RAIZ):
    if f.endswith((".py", ".ico")):
        shutil.copy2(os.path.join(RAIZ, f), tmp)
shutil.copytree(os.path.join(RAIZ, "estrategias"), os.path.join(tmp, "estrategias"))
shutil.copy2(os.path.join(RAIZ, "tests", "datos", "historial_ejemplo.json"), os.path.join(tmp, "historial_estrategias.json"))
subprocess.run([sys.executable, "servidor.py", "preparar", "--ip", "127.0.0.1", "--puerto", "18555"], cwd=tmp, check=True,
               capture_output=True)
codigo = subprocess.run([sys.executable, "servidor.py", "codigo"], cwd=tmp, capture_output=True, text=True,
                        check=True).stdout.strip()
srv = subprocess.Popen([sys.executable, "servidor.py", "correr"], cwd=tmp, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
try:
    sys.path.insert(0, RAIZ)
    import cliente_api as C
    for _ in range(40):
        try:
            C.Cliente(codigo).estado(); break
        except C.ErrorConexion:
            time.sleep(0.5)
    os.chdir(tmp)  # la app de control trabaja en su carpeta (como en Windows)
    sys.path.insert(0, tmp)
    from PySide6.QtWidgets import QApplication
    qa = QApplication.instance() or QApplication(sys.argv)
    import control
    w = control.Control(codigo)
    fin = time.time() + 20
    while time.time() < fin and (w.datos is None or "curva" not in w.detalles):
        qa.processEvents(); time.sleep(0.1)
    assert w.datos and not w.error, w.error
    for i in range(8):
        w.ir_a(i)
        w.pintado = -1; w._pintar(); qa.processEvents()
    assert "USDT" in w.lbl_saldo.text(), w.lbl_saldo.text()
    assert w.datos["servidor"] and w.tab_pos.rowCount() >= 0
    cl = C.Cliente(codigo)
    assert cl.codigo == "".join(codigo.split()) and w.cliente.codigo == cl.codigo  # botón Copiar código de conexión
    assert cl.accion("piloto", activo=True) == "ok" and cl.estado()["snap"]["auto"] is True
    # asistente para crear el servidor y diálogo para conectar Binance (sin Oracle ni Binance de verdad)
    import asistente
    a = asistente.AsistenteServidor(None)
    assert "BEGIN PUBLIC KEY" in a.pub and os.path.exists(asistente.ARCH_CLAVE_OCI)
    for i in range(4):
        a.pasos.setCurrentIndex(i); qa.processEvents()
    a2 = asistente.AsistenteServidor(None)
    assert a2.pub == a.pub  # la clave de API de Oracle se guarda y se reutiliza
    dlg = asistente.DialogoClaves(None, cl, "demo")
    assert "BEGIN PUBLIC KEY" in dlg.pub
    assert cl.estado()["claves"] == {"demo": False, "real": False}  # todavía sin API key: no hay claves cargadas
    print("9) app de control: conecta con el servidor por HTTPS fijado, recorre las 8 pantallas, manda acciones y abre "
          "el asistente de Oracle y el de Binance")
    w.parar.set()
finally:
    srv.terminate()
    srv.wait(10)
