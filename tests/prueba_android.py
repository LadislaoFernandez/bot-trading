"""Prueba de la app de Android en Linux (con Kivy y una pantalla virtual): levanta un servidor de prueba, conecta la app
con el código y recorre todas las pestañas. Falla si la app tira cualquier error."""
import os
import shutil
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tmp = tempfile.mkdtemp(prefix="servidor_android_")
for f in os.listdir(RAIZ):
    if f.endswith(".py"):
        shutil.copy2(os.path.join(RAIZ, f), tmp)
shutil.copytree(os.path.join(RAIZ, "estrategias"), os.path.join(tmp, "estrategias"))
shutil.copy2(os.path.join(RAIZ, "tests", "datos", "historial_ejemplo.json"), os.path.join(tmp, "historial_estrategias.json"))
subprocess.run([sys.executable, "servidor.py", "preparar", "--ip", "127.0.0.1", "--puerto", "18666"], cwd=tmp, check=True,
               capture_output=True)
codigo = subprocess.run([sys.executable, "servidor.py", "codigo"], cwd=tmp, capture_output=True, text=True,
                        check=True).stdout.strip()
srv = subprocess.Popen([sys.executable, "servidor.py", "correr"], cwd=tmp, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
errores = []
try:
    time.sleep(4)
    sys.path.insert(0, os.path.join(RAIZ, "android"))
    sys.path.insert(1, RAIZ)  # cliente_api.py (en el APK se copia a la carpeta de la app)
    os.environ["KIVY_NO_ARGS"] = "1"
    from kivy.base import ExceptionHandler, ExceptionManager
    from kivy.clock import Clock

    class Guardar(ExceptionHandler):
        def handle_exception(self, e):
            errores.append(repr(e))
            return ExceptionManager.PASS
    ExceptionManager.add_handler(Guardar())
    import main as M
    M.ControlApp._leer_codigo = lambda self: codigo
    app = M.ControlApp()
    pasos = ["resumen", "posiciones", "operaciones", "estrategias", "decisiones", "avisos", "control", "servidor",
             "resumen"]

    def paso(dt):
        if not app.datos:
            return
        if pasos:
            app._ir(pasos.pop(0))
        else:
            app.stop()
    Clock.schedule_interval(paso, 1.5)
    Clock.schedule_once(lambda dt: app.stop(), 60)
    app.run()
    assert app.datos and not app.error, app.error
    assert not errores, errores
    # servicio de avisos: una vuelta contra el servidor real (la parte de Android solo muestra la notificación)
    import avisos as AV
    import cliente_api as C
    vistos, avisados = os.path.join(tmp, "vistos.json"), []
    cli = C.Cliente(codigo)
    assert "eventos" in cli.detalle("eventos")
    AV.ciclo(cli, vistos, lambda *a: avisados.append(a))
    AV.ciclo(cli, vistos, lambda *a: avisados.append(a))
    assert os.path.exists(vistos) and not avisados  # sin operaciones nuevas, no avisa nada
    print("10) app de Android: conecta con el servidor, recorre las 8 pestañas sin errores y el servicio de avisos "
          "lee los eventos del servidor")
finally:
    srv.terminate()
    srv.wait(10)
