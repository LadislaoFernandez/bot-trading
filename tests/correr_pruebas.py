"""Pruebas del bot. Corren antes de cada publicación (GitHub Actions) y se pueden correr a mano:

    python tests/correr_pruebas.py

1. Simulado contra backtest: hora a hora, el bot da exactamente lo mismo que el backtest.
2. Piloto automático: el dinero cuadra, reequilibra una vez por día y la revisión mensual saca a la que falla.
3. Binance falso: en cada vela, las posiciones del bot coinciden con las de Binance y cada una tiene su stop.
4. Actualizador: reemplaza el código, respalda la versión anterior y no toca los datos del usuario.
Usa velas sintéticas (tests/datos), no necesita internet.
"""
import csv
import gzip
import importlib
import json
import os
import random
import shutil
import sys
import tempfile
import time
import zipfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
with gzip.open(os.path.join(RAIZ, "tests", "datos", "syn1h.json.gz"), "rt") as f:
    ROWS = json.load(f)
HIST = os.path.join(RAIZ, "tests", "datos", "historial_ejemplo.json")


def carpeta_nueva():
    d = tempfile.mkdtemp(prefix="bot_prueba_")
    os.chdir(d)
    return d


def modulos():
    import config as K
    import paper_trader as PT
    import live as L
    import backtest
    for m in (K, PT, L, backtest):
        importlib.reload(m)
    import config as K, paper_trader as PT, live as L, backtest  # noqa: E401
    return K, PT, L, backtest


def reloj_falso(PT, logs):
    clock = {"t": 0}
    PT.now_ms = lambda: clock["t"]
    PT.log = lambda m: logs.append(m)
    PT.fetch_recent = lambda ex, sym, tf, limit=1500: [r for r in ROWS if r[0] <= clock["t"]][-limit:]
    return clock


def prueba_backtest():
    carpeta_nueva()
    K, PT, L, backtest = modulos()
    PT.configurar_modo("simulado"); K.SYMBOLS = {"SYN": "x"}
    logs = []; clock = reloj_falso(PT, logs)
    st = PT.load_state()
    for k in range(3000, 4500):
        clock["t"] = ROWS[k][0] + 20000
        PT.step(None, st)
    _, res = backtest.run(ROWS[2999][0], ROWS[4499][0], {"SYN": ROWS})
    for k, (eq, *_r) in res.items():
        assert abs(st["sleeves"][k]["equity"] - eq) < 1e-6, (k, st["sleeves"][k]["equity"], eq)
    print("1) simulado = backtest:", {k: round(v[0], 4) for k, v in res.items()})


def prueba_auto():
    """Piloto: solo usa las estrategias base, reequilibra una vez por día en partes iguales sin perder un centavo, y la
    revisión mensual saca a una estrategia que falla 3 meses seguidos (y avisa)."""
    d = carpeta_nueva()
    with open(HIST, encoding="utf-8") as f:
        h = json.load(f)
    h["estrategias"]["TL"]["semestres"] = [-8.0, -4.0, 20.0, 15.0]   # perdió en los últimos 12 meses: falla
    h["estrategias"]["BREAKOUT"]["semestres"] = [9.0, 6.0, 12.0, -3.0]  # ganó: pasa
    with open(os.path.join(d, "historial_estrategias.json"), "w", encoding="utf-8") as f:
        json.dump(h, f)
    K, PT, L, backtest = modulos()
    import auto, alertas
    importlib.reload(alertas); importlib.reload(auto)
    PT.configurar_modo("simulado"); K.SYMBOLS = {"SYN": "x"}
    logs = []; clock = reloj_falso(PT, logs)
    PT.guardar_activas(["SUPERTREND"])  # lo manual no cuenta con el piloto encendido
    PT.guardar_auto(activo=True)
    st = PT.load_state()
    usadas, dentro_por_mes = set(), {}
    original = PT.aplicar_asignacion

    def revisar(st, act, asig=None):  # justo después de repartir: todo cuadra antes de operar
        tot0 = sum(v["equity"] for v in st["sleeves"].values()) + st.get("libre", 0.0)
        original(st, act, asig)
        tot = sum(v["equity"] for v in st["sleeves"].values()) + st["libre"]
        assert abs(tot - tot0) < 1e-6 and st["libre"] > -1e-9, (tot0, tot, st["libre"])
        objetivos = {kk: v for kk, v in (asig or {}).items() if v > 0}
        if st["auto"].get("reequilibrio_hora") != revisar.ultimo:  # recién reequilibrado: reparte lo que hay, ni más
            revisar.ultimo = st["auto"].get("reequilibrio_hora")
            assert sum(objetivos.values()) <= tot + 0.05, (sum(objetivos.values()), tot)
        if len(set(round(v, 2) for v in objetivos.values())) > 1:
            raise AssertionError(("partes distintas", objetivos))
    revisar.ultimo = None
    PT.aplicar_asignacion = revisar
    for k in range(3000, 6000):
        clock["t"] = ROWS[k][0] + 20000
        PT.step(None, st)
        usadas.update(st["efectivo"]["activas"]["SYN"])
        dentro_por_mes[st["auto"]["mes"]] = list(st["auto"]["dentro"])
    reeq = [l for l in logs if "reequilibrio diario" in l]
    dias = (ROWS[5999][0] - ROWS[3000][0]) / 86400000
    assert usadas <= {"BREAKOUT", "TL"} and "BREAKOUT" in usadas, usadas
    assert dias - 2 <= len(reeq) <= dias + 6, (len(reeq), dias)  # una vez por día (más si cambió la cartera)
    meses = sorted(dentro_por_mes)
    assert "TL" in dentro_por_mes[meses[1]] and "TL" not in dentro_por_mes[meses[2]], dentro_por_mes
    assert dentro_por_mes[meses[-1]] == ["BREAKOUT"], dentro_por_mes
    avisos = [a["titulo"] for a in alertas.listar()]
    assert any("deja de recibir dinero" in x for x in avisos) and any("falló la revisión" in x for x in avisos), avisos
    ops = list(csv.DictReader(open(K.TRADES_FILE, encoding="utf-8")))
    print(f"2) piloto automático: {len(ops)} operaciones, {len(reeq)} reequilibrios en {dias:.0f} días, "
          f"revisión mensual: {dentro_por_mes}")


def prueba_binance(semilla, auto=False):
    d = carpeta_nueva()
    shutil.copy(HIST, os.path.join(d, "historial_estrategias.json"))
    K, PT, L, backtest = modulos()
    from fake_binance import FakeBinance
    random.seed(semilla)
    rows2 = [[r[0], r[1] / 300, r[2] / 300, r[3] / 300, r[4] / 300] for r in ROWS]
    K.SYMBOLS = {"BTC": "BTC/USDT:USDT", "SOL": "SOL/USDT:USDT"}
    PT.configurar_modo("demo"); K.INITIAL_CAPITAL = 100.0; K.ESPERA_ORDEN_LIMITE = 60
    clock = {"t": 0}
    fake = FakeBinance({"BTC/USDT:USDT": ROWS, "SOL/USDT:USDT": rows2}, clock,
                       {"BTC/USDT:USDT": (100, 0.001), "SOL/USDT:USDT": (5, 0.01)})
    br = object.__new__(L.Broker); br.ex = fake; br.modo = "demo"; br.preparado = set()
    t_real, s_real = time.time, time.sleep
    time.time = lambda: clock["t"] / 1000
    time.sleep = lambda s: clock.__setitem__("t", clock["t"] + s * 1000)
    try:
        logs = []; PT.log = lambda m: logs.append(m)
        PT.guardar_activas(["BREAKOUT", "TL", "SUPERTREND"])
        if auto:
            PT.guardar_auto(activo=True)
        st = PT.load_state()
        sys.path.insert(0, os.path.join(RAIZ, "android"))
        import avisos as AV
        import servidor as SV  # al importarse se para en la carpeta del código: volver a la de la prueba
        os.chdir(d)
        vistos, avisados = os.path.join(d, "vistos.json"), []
        AV.nuevos(SV.eventos_operaciones("."), vistos)  # primera vez: no avisa nada
        for k in range(3000, 3600):
            fake.procesar_vela("BTC/USDT:USDT", ROWS[k - 1]); fake.procesar_vela("SOL/USDT:USDT", rows2[k - 1])
            clock["t"] = ROWS[k][0] + 20000
            L.step_live(br, st)
            for a, sym in K.SYMBOLS.items():
                for lado in ("long", "short"):
                    q_bot = sum(v["pos"]["q"] for kk, v in st["sleeves"].items()
                                if kk.startswith(a + "_") and v["pos"] and v["pos"]["side"] == lado)
                    assert abs(q_bot - fake.pos.get((sym, lado), 0)) < 1e-6, (k, a, lado)
            for kk, v in st["sleeves"].items():
                if v["pos"]:
                    o = fake.orders.get(v["pos"].get("stop_id"))
                    assert o and o["status"] == "open", (k, kk, "sin stop")
            abiertos = [o for o in fake.orders.values() if o.get("stopord") and o["status"] == "open"]
            assert len(abiertos) == sum(1 for v in st["sleeves"].values() if v["pos"]), (k, "stops huérfanos")
            avisados += AV.nuevos(SV.eventos_operaciones("."), vistos)
        n = L.cerrar_todo(br, st)
        assert not {k: v for k, v in fake.pos.items() if v > 1e-9}
        avisados += AV.nuevos(SV.eventos_operaciones("."), vistos)
        # notificaciones del celular: un aviso por cada apertura y por cada cierre, sin repetir
        import app_data as A
        ops = A.operaciones(".")
        ids = [e["id"] for e in avisados]
        assert len(ids) == len(set(ids)), "aviso repetido"
        assert sum(e["tipo"] == "cierra" for e in avisados) == len(ops), (len(avisados), len(ops))
        assert {e["id"] for e in avisados if e["tipo"] == "abre"} == {f"a|{o['activo']}|{o['clave']}|{o['entrada_t']}" for o in ops}
        assert all(AV.texto(e, "Demo")[0] for e in avisados)
        assert not AV.nuevos(SV.eventos_operaciones("."), vistos)
        # aviso de app nueva: una sola vez por versión, y sin borrar los avisos ya vistos
        assert AV.version_nueva("1.13", "1.12") and not AV.version_nueva("1.12", "1.12") and not AV.version_nueva("1.12", None)
        assert AV.avisar_version("1.13", "1.12", vistos) == "1.13" and AV.avisar_version("1.13", "1.12", vistos) is None
        assert not AV.nuevos(SV.eventos_operaciones("."), vistos)
        txt = "\n".join(logs)
        print(f"3) Binance falso (semilla {semilla}{', modo automático' if auto else ''}): {txt.count('abrió')} aperturas, "
              f"{txt.count('Binance ejecutó el stop')} stops ejecutados, cerrar todo cerró {n}; todo coincide; "
              f"{len(avisados)} avisos al celular, uno por apertura y por cierre")
    finally:
        time.time, time.sleep = t_real, s_real


def prueba_reglas():
    import engine as E
    import reglas as R
    from equivalentes import EQUIVALENTES
    for esc in (1, 1 / 300):
        rr = [[r[0], r[1] * esc, r[2] * esc, r[3] * esc, r[4] * esc] for r in ROWS]
        D = E.prepare(rr, 3600000, 4 * 3600000)
        for k, d in EQUIVALENTES.items():
            assert not R.validar(d), (k, R.validar(d))
            E.STRATS[d["id"]] = R.compilar(d)
            res = []
            for s in (k, d["id"]):
                sl = E.Sleeve(s, 0.03, 10, 0.0002, 0, 100.0); n = 0
                for i in range(1, D["n"]):
                    sl.on_bar(D, i); n += len(sl.closed); sl.closed = []
                res.append((round(sl.equity, 9), n))
            assert res[0] == res[1], (k, res)
            del E.STRATS[d["id"]]
            R.explicar(d, D, D["n"] - 1); R.describir(d)
    assert R.validar({"id": "x", "entrada": [{"a": "NOEXISTE", "op": ">", "b": 1}]})
    assert R.validar({"id": "../x", "entrada": [{"a": "C", "op": ">", "b": "EMA200"}]})
    print("5) estrategias como datos: las 6 originales escritas como datos dan exactamente lo mismo que las de código")


def prueba_laboratorio():
    d = carpeta_nueva()
    import catalogo
    import engine as E
    import laboratorio as L
    import reglas as R
    os.chdir(d)
    ahora = int(time.time() * 1000)
    off = ahora - ROWS[-1][0]
    Ds = {}
    for k, esc in (("A", 1), ("B", 1 / 300), ("C", 1 / 20)):
        rr = [[r[0] + off, r[1] * esc, r[2] * esc, r[3] * esc, r[4] * esc] for r in ROWS]
        Ds[k] = R.completar(E.prepare(rr, 3600000, 4 * 3600000))
    L.DESDE = time.strftime("%Y-%m-%d", time.gmtime(Ds["A"]["T"][300] / 1000))
    L.CORTE = time.strftime("%Y-%m-%d", time.gmtime(Ds["A"]["T"][3500] / 1000))
    nuevas = L.correr(0.15, semilla=1, Ds=Ds, log=lambda m: None)
    assert nuevas and len(nuevas) <= L.MAX_NUEVAS, len(nuevas)
    assert len({n["_familia"] for n in nuevas}) == len(nuevas)
    for n in nuevas:
        assert not R.validar(n) and n["validacion"]["prueba"]["pf"] >= L.PF_PRUEBA
        assert n["estado"] == "observacion" and n["observacion"]["desde"] == Ds["A"]["T"][-1] and n["examen"]
    raiz_antes = catalogo.RAIZ
    try:
        catalogo.RAIZ = d
        catalogo.guardar_propia(nuevas[0])
        strats, nombres = {}, {}
        catalogo.cargar(strats, nombres)
        assert nuevas[0]["id"] in strats and catalogo.DEFINICIONES[nuevas[0]["id"]]["_origen"] == "mis_estrategias"
        catalogo.quitar_propia(nuevas[0]["id"])
    finally:
        catalogo.RAIZ = raiz_antes
        catalogo.cargar({}, {})
    otra = L.correr(0.1, semilla=1, Ds=Ds, log=lambda m: None)  # no repite lo ya propuesto
    assert not {n["_familia"] for n in otra} & {n["_familia"] for n in nuevas}
    # observación: a los 90 días se decide sola (asciende al piloto o se descarta), sin dinero
    import alertas, archivos
    raiz_antes = catalogo.RAIZ
    try:
        catalogo.RAIZ = d
        for n in nuevas:
            p_ = os.path.join("candidatas", n["id"] + ".json")
            dd = json.load(open(p_, encoding="utf-8"))
            dd["observacion"]["desde"] = Ds["A"]["T"][-1] - 100 * 86400000
            json.dump(dd, open(p_, "w", encoding="utf-8"))
        asc, desc = L.revisar_observacion(Ds, log=lambda m: None)
        assert sorted(asc + desc) == sorted(n["id"] for n in nuevas), (asc, desc)
        for x in asc:
            assert os.path.exists(os.path.join(d, "mis_estrategias", x + ".json"))
            assert x in archivos.leer_json("ajustes.json", {})["piloto_extra"]
        for x in desc:
            assert os.path.exists(os.path.join("candidatas", "descartadas", x + ".json"))
        quedan = {f[:-5] for f in os.listdir("candidatas") if f.startswith("LAB_")}
        assert not quedan & {n["id"] for n in nuevas} and quedan == {n["id"] for n in otra}, quedan  # las nuevas siguen en observación
        avisos = [a["titulo"] for a in alertas.listar()]
        assert len([a for a in avisos if "entra al piloto" in a or "se descartó" in a]) == len(nuevas), avisos
    finally:
        catalogo.RAIZ = raiz_antes
        catalogo.cargar({}, {})
    print(f"6) laboratorio: {len(nuevas)} candidatas aprobaron el examen, sin repetir familias; a los 3 meses de "
          f"observación {len(asc)} entró al piloto y {len(desc)} se descartó")


def prueba_reparto():
    import auto
    importlib.reload(auto)
    minimo = lambda k, a: {"BTC": 60, "ETH": 9, "SOL": 3}[a]
    m, afuera = auto.repartir(360, ["BTC_TL", "BTC_BREAKOUT", "ETH_TL", "ETH_BREAKOUT", "SOL_TL", "SOL_BREAKOUT"], minimo)
    assert set(m.values()) == {60.0} and not afuera, m
    m, afuera = auto.repartir(250, ["BTC_TL", "BTC_BREAKOUT", "ETH_TL", "ETH_BREAKOUT", "SOL_TL", "SOL_BREAKOUT"], minimo)
    assert set(afuera) == {"BTC_TL", "BTC_BREAKOUT"} and all(abs(v - 62.5) < 0.01 for v in m.values()), (m, afuera)
    m, afuera = auto.repartir(100, ["BTC_TL"], minimo)
    assert m == {"BTC_TL": 100.0}
    m, afuera = auto.repartir(30, ["BTC_TL"], minimo)
    assert m == {} and afuera == ["BTC_TL"]
    import mercado as M
    h = {"estrategias": {"A": {"semestres": [5, -2, 10, 10]}, "B": {"semestres": [-5, 2, 10, 10]}, "C": {"semestres": [5, 5]}}}
    assert M.califica(h, "A")[0] is True and M.califica(h, "B")[0] is False and M.califica(h, "C")[0] is None
    # una estrategia que entra al piloto (del laboratorio) empieza en uso, y una que se quitó sale sin romper nada
    importlib.reload(auto)
    auto.base = lambda: ["BREAKOUT", "TL", "CRUCE"]
    st = {"sleeves": {}, "libre": 300.0, "capital_inicial": 300.0, "aportes": 0.0,
          "auto": {"dentro": ["BREAKOUT", "TL", "VIEJA"], "conocidas": ["BREAKOUT", "TL", "VIEJA"], "racha": {}}}
    act, asig = auto.plan(st, None)
    import config as K_
    assert st["auto"]["dentro"] == ["BREAKOUT", "TL", "CRUCE"] and len(asig) == 3 * len(K_.SYMBOLS), (st["auto"]["dentro"], asig)
    importlib.reload(auto)
    print("7) reparto en partes iguales y revisión: respeta el mínimo de Binance y juzga solo con 2 años de historial")


def prueba_actualizador():
    import actualizador as AC
    import config as K
    d = carpeta_nueva()
    app = os.path.join(d, "app"); os.makedirs(app)
    for f, txt in {"app.py": "viejo", "config.py": "viejo", "requirements.txt": "", "ajustes.json": '{"modo":"demo"}',
                   "estado_demo.json": "{}", "claves_demo.dat": "x"}.items():
        open(os.path.join(app, f), "w").write(txt)
    zp = os.path.join(d, "actualizacion.zip")
    with zipfile.ZipFile(zp, "w") as z:
        z.writestr("app.py", "nuevo"); z.writestr("config.py", "nuevo"); z.writestr("requirements.txt", "")
        z.writestr("auto.py", "nuevo"); z.writestr("ajustes.json", "{}")  # este no debe pisarse
        z.writestr("estrategias/NUEVA.json", "{}"); z.writestr("mis_estrategias/X.json", "{}")  # catálogo sí, propias no
    info = dict(version="99.0", url="file://" + zp.replace("\\", "/"), tamano=os.path.getsize(zp))
    hechos = AC.instalar(info, carpeta=app)
    leer = lambda f: open(os.path.join(app, f)).read()
    assert leer("app.py") == "nuevo" and leer("auto.py") == "nuevo" and leer("estrategias/NUEVA.json") == "{}"
    assert not os.path.exists(os.path.join(app, "mis_estrategias"))
    assert leer("ajustes.json") == '{"modo":"demo"}' and leer("claves_demo.dat") == "x"
    assert open(os.path.join(app, "respaldos", K.VERSION, "app.py")).read() == "viejo"
    assert AC.version_tupla("v1.10") > AC.version_tupla("1.9") > AC.version_tupla("1.4.1") > AC.version_tupla("1.4")
    print(f"4) actualizador: {len(hechos)} archivos reemplazados, datos del usuario intactos, respaldo guardado")


if __name__ == "__main__":
    t0 = time.time()
    prueba_backtest()
    prueba_auto()
    prueba_binance(4)
    prueba_binance(11, auto=True)
    prueba_actualizador()
    prueba_reglas()
    prueba_laboratorio()
    prueba_reparto()
    print(f"TODO OK en {time.time() - t0:.0f} s")
