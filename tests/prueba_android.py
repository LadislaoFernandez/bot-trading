"""Prueba de la app de Android en Linux (con Kivy y una pantalla virtual): levanta un servidor de prueba, conecta la app
con el código y recorre todas las pestañas. Falla si la app tira cualquier error."""
import os
import shutil
import subprocess
import sys
import tempfile
import time

os.environ["BOT_SIN_RELAY"] = "1"  # que el servidor de prueba no use el intermediario de avisos real

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
    from kivy.core.window import Window

    class Guardar(ExceptionHandler):
        def handle_exception(self, e):
            errores.append(repr(e))
            return ExceptionManager.PASS
    ExceptionManager.add_handler(Guardar())
    import main as M
    M.ControlApp._leer_codigo = lambda self: codigo
    Window.size = (400, 860)  # como un celular
    CAPTURAS = os.environ.get("CAPTURAS")  # carpeta: guarda una foto de cada paso (el CI las sube para revisarlas)

    # datos de ejemplo encima de los del servidor de prueba, para dibujar posiciones, operaciones y avisos
    _estado = M.C.Cliente.estado

    def estado_con_ejemplo(self):
        d = _estado(self)
        s = d["snap"]
        pos = [dict(activo="ETH", estrategia="BREAKOUT", lado="long", pnl=6.82, asignado=120.0, capital=126.8,
                    entrada=2961.4, precio=3002.15, stop=2948.1, riesgo=-1.2),
               dict(activo="SOL", estrategia="TL", lado="short", pnl=-1.37, asignado=120.0, capital=118.6,
                    entrada=187.22, precio=188.4, stop=191.05, riesgo=2.9)]
        s["abiertas"] = [dict(f) for f in pos]
        s["posiciones"] = pos + [dict(activo="BTC", estrategia="BREAKOUT", lado=None, asignado=120.0, capital=120.0,
                                      entrada=None, precio=None, stop=None, riesgo=None, pnl=None)]
        s.setdefault("ultimas_operaciones", [])
        s["ultimas_operaciones"] = [dict(activo="BTC", estrategia="TL", lado="long", salida_t="2026-11-10 14:00",
                                         motivo="stop", pnl=4.1)] + list(s["ultimas_operaciones"])
        d["alertas"] = [dict(titulo="Abrió ETH Breakout", hora=time.time() - 3600, texto="Compra a 2.961,40.",
                             leida=False)] + list(d.get("alertas") or [])
        return d
    M.C.Cliente.estado = estado_con_ejemplo
    app = M.ControlApp()
    resultado = {}
    pasos = ["resumen", lambda: app._abrir_menu(), lambda: app._cerrar_menu(), "posiciones", "operaciones", "estrategias", "decisiones", "avisos", "control", "servidor",
             # asistente de Oracle y conexión de Binance (pantallas; la creación real se prueba en correr_pruebas)
             lambda: app._pantalla_codigo(), lambda: app._asistente_inicio(), lambda: app._asistente_clave(),
             lambda: app._asistente_clave("error de prueba"), lambda: app._asistente_progreso(),
             lambda: app._log("línea de prueba"), lambda: app._asistente_error("falla de prueba"),
             lambda: app._asistente_listo(codigo, "127.0.0.1", "VM.Standard.E2.1.Micro"),
             lambda: app._pantalla_claves("demo"), lambda: None, lambda: app._pantalla_claves("real"), lambda: None,
             lambda: app._volver_inicio(), "resumen",
             # modo claro
             lambda: app._cambiar_tema("claro"), "posiciones", "decisiones", lambda: app._abrir_menu(),
             lambda: app._cerrar_menu(), "servidor", lambda: app._cambiar_tema("oscuro"),
             # tarjeta de versión nueva (en la PC no se actualiza sola) y el refresco que no vuelve arriba
             lambda: (setattr(app, "version_app", "0.1"), app._ir("resumen")),
             lambda: (setattr(app, "version_app", None), setattr(Window, "size", (360, 300)), app._ir("estrategias")),
             lambda: marcar_scroll(),
             lambda: app._pintar(desde_sondeo=True),
             lambda: comprobar_scroll(), "resumen"]

    def marcar_scroll():
        sv = app.cuerpo.children[0]
        sv.scroll_y = 0.3
        resultado["antes"] = (sv.scroll_y, sv.children[0].height, sv.height)

    def comprobar_scroll():
        sv = app.cuerpo.children[0]
        assert resultado["antes"][1] > resultado["antes"][2], f"el contenido no llega a deslizarse: {resultado['antes']}"
        assert abs(sv.scroll_y - 0.3) < 1e-6, (sv.scroll_y, sv.children[0].height, sv.height, resultado["antes"])
        resultado["scroll"] = True

    def paso(dt):
        if not app.datos:
            return
        if pasos:
            p = pasos.pop(0)
            p() if callable(p) else app._ir(p)
            if CAPTURAS:
                n = resultado["foto"] = resultado.get("foto", 0) + 1
                Clock.schedule_once(lambda dt: Window.screenshot(name=os.path.join(CAPTURAS, f"paso{n:02d}.png")), 1.1)
        else:
            app.stop()
    Clock.schedule_interval(paso, 1.5)
    Clock.schedule_once(lambda dt: app.stop(), 150)
    app.run()
    assert app.datos and not app.error, app.error
    assert not errores, errores
    assert resultado.get("scroll"), "al refrescar, la pantalla volvió arriba"
    # avisos push: el celular se registra en el servidor (sin clave de Firebase el servidor lo acepta igual)
    import cliente_api as C
    cli = C.Cliente(codigo)
    assert "eventos" in cli.detalle("eventos")
    assert cli.accion("push_registrar", token="token-de-prueba", version="1.0") == "sin_firebase"
    ep = cli.estado()["push"]
    assert ep["configurado"] is False and ep["celulares"] == 1, ep
    assert cli.accion("push_quitar", token="token-de-prueba") == "ok"
    assert cli.estado()["push"]["celulares"] == 0
    # intermediario de avisos: sin token de la app, pero este servidor no tiene clave de Firebase → lo rechaza
    import push
    info = C.leer_codigo(codigo)
    r = push.Relay({"url": f"https://{info['h']}:{info['p']}", "huella": info["f"]}).enviar("x" * 40, "t", "c")
    assert r.startswith("intermediario HTTP 400"), r
    assert push.Relay({"url": f"https://{info['h']}:{info['p']}", "huella": "0" * 64}).enviar("x" * 40, "t", "c") \
        == "el intermediario no tiene el certificado esperado"
    print("10) app de Android: conecta con el servidor, recorre las 8 pestañas sin errores y se registra para los avisos")
finally:
    srv.terminate()
    srv.wait(10)
