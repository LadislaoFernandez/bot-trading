"""Laboratorio de estrategias: busca estrategias nuevas combinando las piezas que ya usa el bot. Corre en un proceso
aparte, con prioridad baja, una vez por semana.

    python laboratorio.py --minutos 30

Cómo decide (para no engañarse con estrategias que solo "funcionaron de casualidad"):
  1. Arma combinaciones al azar de un filtro de tendencia o de mercado, un disparo de entrada, a lo sumo una condición
     extra, una salida y un stop, y mejora las mejores cambiando de a una pieza.
  2. Las elige SOLO con velas desde 2022 hasta hace 12 meses: al menos 60 operaciones sumando BTC, ETH y SOL, y ganar al
     menos 1,2 veces lo que pierde. Los últimos 12 meses no los mira mientras busca.
  3. Examen final: las 5 mejores de la corrida (una por familia) rinden un examen con los últimos 12 meses, una sola vez
     cada una: al menos 30 operaciones, ganar 1,15 veces lo que pierde, positiva en al menos 2 de las 3 monedas, en
     cada semestre del examen menos uno como mucho y en los 12 meses.
  4. Observación: la que aprueba queda 3 meses en observación, SIN dinero: el laboratorio calcula cada semana cómo le va
     desde que aprobó, con las mismas comisiones, y lo compara con Breakout y Resorte de tendencia en el mismo período.
     A los 3 meses, si ganó y le fue al menos tan bien como ellas, entra al piloto automático con una parte igual; si
     no, se descarta. Las dos cosas quedan en Avisos.
En la prueba con datos de 2024 a 2026, entrar a probar con dinero costaba plata (las candidatas que aprobaron el examen
perdieron en sus primeros meses); observar sin dinero no costaba nada.
"""
import argparse
import copy
import hashlib
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone

RAIZ = os.path.dirname(os.path.abspath(__file__))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)

import config as K  # noqa: E402
import engine as E  # noqa: E402
import reglas as R  # noqa: E402

CARPETA = "candidatas"
DATOS = "datos_lab"
ESTADO = "laboratorio_estado.json"
PROBADAS = os.path.join(CARPETA, "probadas.json")  # firmas ya evaluadas fuera de muestra (no se repiten)
DESDE = "2022-01-01"
CORTE = None  # antes: búsqueda; desde acá: examen final. Si no se fija, son los últimos 12 meses.
OBSERVACION_DIAS = 90
RIESGO, APAL, COMISION = 0.03, 10, 0.0005  # comisión de orden a mercado, más exigente que la del bot (0,02 %)

MIN_OPS_ENTRENO, PF_ENTRENO = 60, 1.20
MIN_OPS_PRUEBA, PF_PRUEBA = 30, 1.15
FINALISTAS = 5       # cuántas rinden el examen final por corrida (pocas, para no "gastar" los datos del examen)
MAX_NUEVAS = 2       # cuántas candidatas nuevas puede proponer por corrida


def _ms(fecha):
    return int(datetime.strptime(fecha, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


# ------------------------------------------------------------------ piezas
FILTROS = [[], [{"a": "C", "op": ">", "b": "EMA200"}], [{"a": "EMA50", "op": ">", "b": "EMA200"}],
           [{"a": "trend", "op": ">", "b": 0}], [{"a": "ST", "op": ">", "b": 0}],
           [{"a": "ADX", "op": ">", "b": 20}], [{"a": "ADX", "op": ">", "b": 25}], [{"a": "ADX", "op": "<", "b": 20}],
           [{"a": "ADX", "op": "<", "b": 25}], [{"a": "C", "op": ">", "b": "EMA200"}, {"a": "ADX", "op": ">", "b": 20}],
           [{"a": "EMA50", "op": ">", "b": "EMA200"}, {"a": "trend", "op": ">", "b": 0}]]
DISPAROS = [
    ("ruptura", {"a": "C", "op": ">", "b": "DH48", "b_desfase": 1}),
    ("cruce_precio", {"a": "C", "op": "cruza_arriba", "b": "EMA20"}),
    ("cruce_precio", {"a": "C", "op": "cruza_arriba", "b": "EMA50"}),
    ("cruce_precio", {"a": "C", "op": "cruza_arriba", "b": "SMA20"}),
    ("banda", {"a": "C", "op": "cruza_arriba", "b": "BBU"}),
    ("banda_baja", {"a": "C", "op": "<", "b": "BBL"}),
    ("cruce_medias", {"a": "EMA20", "op": "cruza_arriba", "b": "EMA50"}),
    ("rsi_bajo", {"a": "RSI14", "op": "<", "b": 30}),
    ("rsi_cruce", {"a": "RSI14", "op": "cruza_arriba", "b": 50}),
    ("rsi_cruce", {"a": "RSI14", "op": "cruza_arriba", "b": 30}),
    ("rsi2", {"a": "RSI2", "op": "<", "b": 10}),
    ("momentum", {"a": "V", "op": "gira_arriba"}),
    ("momentum_cruce", {"a": "V", "op": "cruza_arriba", "b": 0}),
    ("supertrend", {"a": "ST", "op": "cruza_arriba", "b": 0}),
]
EXTRAS = [None, {"a": "ADX", "op": "sube", "n": 3}, {"a": "ADX", "op": "cae", "n": 3, "desfase": 1},
          {"op": "squeeze", "n": 6}, {"a": "RSI14", "op": ">", "b": 50}, {"a": "RSI14", "op": "<", "b": 70},
          {"a": "V", "op": ">", "b": 0}]
SALIDAS = [[], [{"a": "C", "op": "cruza_abajo", "b": "EMA20"}], [{"a": "C", "op": "cruza_abajo", "b": "SMA20"}],
           [{"a": "C", "op": "cruza_abajo", "b": "EMA50"}], [{"a": "RSI14", "op": ">", "b": 70}],
           [{"a": "C", "op": ">", "b": "SMA5"}], [{"a": "V", "op": "cruza_abajo", "b": 0}], [{"a": "ST", "op": "<", "b": 0}],
           [{"a": "EMA20", "op": "<", "b": "EMA50"}], [{"a": "C", "op": ">=", "b": "SMA20"}]]
UMBRALES = {"RSI14": [25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75], "RSI2": [5, 10, 15, 20], "ADX": [15, 20, 25, 30]}
STOPS, TRAILS, MAXV = [1.5, 2, 2.5, 3], [0, 2, 3, 4], [0, 0, 12, 24, 48]
NOMBRE_DISPARO = {
    "ruptura": ("Ruptura de 48 h", "48 h breakout"), "cruce_precio": ("Cruce de precio y media", "Price and average cross"),
    "banda": ("Ruptura de Bollinger", "Bollinger breakout"), "banda_baja": ("Rebote en Bollinger", "Bollinger bounce"),
    "cruce_medias": ("Cruce 20/50", "20/50 cross"), "rsi_bajo": ("Sobreventa RSI", "RSI oversold"),
    "rsi_cruce": ("Giro de RSI", "RSI turn"), "rsi2": ("Caída corta RSI(2)", "Short RSI(2) dip"),
    "momentum": ("Giro de momentum", "Momentum turn"), "momentum_cruce": ("Momentum positivo", "Positive momentum"),
    "supertrend": ("Giro de Supertrend", "Supertrend turn"),
}


def _armar(d):
    p = d["_partes"]
    extra = [copy.deepcopy(p["extra"])] if p["extra"] and p["extra"] not in p["filtro"] else []
    d["entrada"] = copy.deepcopy(p["filtro"]) + [copy.deepcopy(p["disparo"])] + extra
    return d


def nueva(rng):
    tipo, disparo = rng.choice(DISPAROS)
    d = dict(direccion=rng.choice(["ambas", "ambas", "largo"]), salida=copy.deepcopy(rng.choice(SALIDAS)),
             stop_atr=rng.choice(STOPS), trail_atr=rng.choice(TRAILS), max_velas=rng.choice(MAXV), _tipo=tipo,
             _partes=dict(filtro=copy.deepcopy(rng.choice(FILTROS)), disparo=copy.deepcopy(disparo),
                          extra=copy.deepcopy(rng.choice(EXTRAS))))
    return _armar(d)


def mutar(d, rng):
    d = copy.deepcopy(d)
    p = d["_partes"]
    que = rng.choice(["umbral", "umbral", "stop", "trail", "max", "salida", "filtro", "extra", "direccion"])
    if que == "umbral":
        cs = [c for c in p["filtro"] + [p["disparo"]] + ([p["extra"]] if p["extra"] else []) + d["salida"]
              if c.get("a") in UMBRALES and not isinstance(c.get("b"), str)]
        if cs:
            c = rng.choice(cs); c["b"] = rng.choice(UMBRALES[c["a"]])
    elif que == "stop":
        d["stop_atr"] = rng.choice(STOPS)
    elif que == "trail":
        d["trail_atr"] = rng.choice(TRAILS)
    elif que == "max":
        d["max_velas"] = rng.choice(MAXV)
    elif que == "salida":
        d["salida"] = copy.deepcopy(rng.choice(SALIDAS))
    elif que == "direccion":
        d["direccion"] = rng.choice(["ambas", "largo"])
    elif que == "filtro":
        p["filtro"] = copy.deepcopy(rng.choice(FILTROS))
    else:
        p["extra"] = copy.deepcopy(rng.choice(EXTRAS))
    return _armar(d)


def familia(d):
    """Misma idea con otros números (mismo disparo y mismo filtro): se propone una sola por familia."""
    p = d.get("_partes") or {}
    clave = [d.get("_tipo"), json.dumps(p.get("disparo"), sort_keys=True), json.dumps(p.get("filtro"), sort_keys=True)]
    return hashlib.sha1(json.dumps(clave).encode()).hexdigest()[:10]


def firma(d):
    clave = dict(direccion=d["direccion"], entrada=sorted(json.dumps(c, sort_keys=True) for c in d["entrada"]),
                 salida=sorted(json.dumps(c, sort_keys=True) for c in d["salida"]), stop=d["stop_atr"],
                 trail=d["trail_atr"], max=d["max_velas"])
    return hashlib.sha1(json.dumps(clave, sort_keys=True).encode()).hexdigest()[:10]


# ------------------------------------------------------------------ datos y evaluación
def velas(asset, sym, log):
    """Velas de 1 h desde DESDE (con margen para los indicadores), guardadas en datos_lab/ y completadas al día."""
    import ccxt
    from data import fetch_range
    os.makedirs(DATOS, exist_ok=True)
    p = os.path.join(DATOS, f"{asset}.json")
    rows = []
    if os.path.exists(p):
        try:
            with open(p) as f:
                rows = json.load(f)
        except ValueError:
            rows = []
    ahora = int(time.time() * 1000)
    desde = rows[-1][0] + K.BAR_MS if rows else _ms("2021-12-01")
    if ahora - desde > K.BAR_MS:
        log(f"bajando velas de {asset}")
        ex = ccxt.binanceusdm({"enableRateLimit": True})
        nuevas = fetch_range(ex, sym, K.TIMEFRAME, desde, ahora)
        vistos = {r[0] for r in rows}
        rows += [r for r in nuevas if r[0] not in vistos]
        rows.sort(key=lambda r: r[0])
        with open(p, "w") as f:
            json.dump(rows, f)
    return [r for r in rows if r[0] + K.BAR_MS <= ahora]


def evaluar(d, Ds):
    """Corre la estrategia en cada moneda. Devuelve los resultados de entrenamiento y de prueba."""
    S = R.compilar(d)
    E.STRATS["_LAB"] = S
    corte, inicio = _ms(CORTE), _ms(DESDE)
    res = {"entreno": [], "prueba": [], "por_moneda": {}, "por_anio": {}, "meses": {}}
    try:
        for a, D in Ds.items():
            sl = E.Sleeve("_LAB", RIESGO, APAL, COMISION, 0.0, 100.0)
            eq_ent, prueba_a = None, []
            for i in range(1, D["n"]):
                if D["T"][i] < inicio:
                    continue
                tenia, eq_antes = sl.pos is not None, sl.equity
                sl.on_bar(D, i)
                if not tenia and sl.pos is not None:
                    eq_ent = eq_antes
                for tr in sl.closed:
                    pct = tr["pnl"] / (eq_ent or eq_antes) * 100
                    eq_ent = sl.equity if sl.pos is not None else None
                    (res["prueba"] if tr["entrada_t"] >= corte else res["entreno"]).append(pct)
                    if tr["entrada_t"] >= corte:
                        prueba_a.append(pct)
                    anio = datetime.fromtimestamp(tr["entrada_t"] / 1000, timezone.utc).year
                    res["por_anio"][anio] = res["por_anio"].get(anio, 0.0) + pct
                sl.closed = []
                if D["T"][i] >= corte:  # capital al cierre de cada mes de la prueba
                    mes = datetime.fromtimestamp(D["T"][i] / 1000, timezone.utc).strftime("%Y-%m")
                    res["meses"].setdefault(a, {})[mes] = sl.mark(D["C"][i])
            res["por_moneda"][a] = dict(ops=len(prueba_a), resultado=sum(prueba_a))
    finally:
        E.STRATS.pop("_LAB", None)
    return res


def semestres_prueba(res, hoy=None):
    """Resultado (en %) de cada semestre completo de la prueba y de los últimos 12 meses, con el capital de la
    estrategia en promedio de las monedas. Solo cuenta meses completos."""
    hoy = (hoy or datetime.now(timezone.utc)).strftime("%Y-%m")
    por_mes = {}
    for a, mm in res.get("meses", {}).items():
        prev = 100.0
        for m in sorted(mm):
            if m >= hoy:
                break
            por_mes.setdefault(m, []).append(mm[m] / prev - 1)
            prev = mm[m]
    meses = sorted(por_mes)
    rend = [sum(por_mes[m]) / len(por_mes[m]) for m in meses]
    sem = []
    for q in range(len(rend) // 6):
        r = 1.0
        for x in rend[q * 6:(q + 1) * 6]:
            r *= 1 + x
        sem.append((r - 1) * 100)
    ult = None
    if len(rend) >= 12:
        r = 1.0
        for x in rend[-12:]:
            r *= 1 + x
        ult = (r - 1) * 100
    return sem, ult


def pf(xs):
    g, p = sum(x for x in xs if x > 0), -sum(x for x in xs if x <= 0)
    return g / p if p > 0 else (99.0 if g > 0 else 0.0)


def puntaje(res, d):
    xs = res["entreno"]
    if len(xs) < MIN_OPS_ENTRENO:
        return -1.0
    complejidad = len(d["entrada"]) + len(d["salida"])
    return (min(pf(xs), 5) - 1) * math.sqrt(len(xs)) / (1 + 0.15 * complejidad)


def aprueba(res):
    """Pruebas fuera de muestra. Devuelve (aprobada, motivos de rechazo)."""
    motivos = []
    ent, pru = res["entreno"], res["prueba"]
    if len(ent) < MIN_OPS_ENTRENO or pf(ent) < PF_ENTRENO:
        motivos.append("entrenamiento flojo")
    if len(pru) < MIN_OPS_PRUEBA:
        motivos.append("pocas operaciones en la prueba")
    if pf(pru) < PF_PRUEBA:
        motivos.append("no gana lo suficiente en la prueba")
    if sum(1 for m in res["por_moneda"].values() if m["resultado"] > 0) < 2:
        motivos.append("positiva en menos de 2 monedas")
    anios = list(res["por_anio"].values())
    if not anios or sum(1 for x in anios if x > 0) < 0.75 * len(anios):
        motivos.append("negativa en demasiados años")
    sem, ult = semestres_prueba(res)
    if sem and sum(1 for x in sem if x <= 0) > 1:
        motivos.append("perdió en más de un semestre de la prueba")
    if ult is not None and ult <= 0:
        motivos.append("perdió en los últimos 12 meses")
    return not motivos, motivos


# ------------------------------------------------------------------ estado y resultado
def _estado(**cambios):
    import archivos
    st = archivos.leer_json(ESTADO, {}) or {}
    st.update(cambios)
    archivos.escribir_json(ESTADO, st, indent=1)
    return st


def _firmas_existentes():
    out = set()
    try:
        with open(PROBADAS) as f:
            out.update(json.load(f))
    except (OSError, ValueError):
        pass
    out.update(_familias_existentes())
    for carpeta in (CARPETA, os.path.join(CARPETA, "descartadas"), os.path.join(CARPETA, "ascendidas"), "mis_estrategias", "estrategias"):
        if os.path.isdir(carpeta):
            for fn in os.listdir(carpeta):
                if fn.endswith(".json") and fn != "probadas.json":
                    try:
                        with open(os.path.join(carpeta, fn), encoding="utf-8") as f:
                            dd = json.load(f)
                        out.add(dd.get("_firma") or firma(dd))
                    except (OSError, ValueError, KeyError):
                        pass
    return out


def _familias_existentes():
    out = set()
    for carpeta in (CARPETA, os.path.join(CARPETA, "descartadas"), os.path.join(CARPETA, "ascendidas"), "mis_estrategias"):
        if os.path.isdir(carpeta):
            for fn in os.listdir(carpeta):
                if fn.startswith("LAB_") and fn.endswith(".json"):
                    try:
                        with open(os.path.join(carpeta, fn), encoding="utf-8") as f:
                            fam = json.load(f).get("_familia")
                        if fam:
                            out.add("fam:" + fam)
                    except (OSError, ValueError):
                        pass
    return out


def _guardar_probadas(firmas):
    os.makedirs(CARPETA, exist_ok=True)
    with open(PROBADAS, "w") as f:
        json.dump(sorted(firmas)[-5000:], f)


def _numero_siguiente():
    n = 0
    for carpeta in (CARPETA, os.path.join(CARPETA, "descartadas"), os.path.join(CARPETA, "ascendidas"), "mis_estrategias"):
        if os.path.isdir(carpeta):
            for fn in os.listdir(carpeta):
                if fn.startswith("LAB_") and fn.endswith(".json"):
                    try:
                        with open(os.path.join(carpeta, fn), encoding="utf-8") as f:
                            n = max(n, int(json.load(f).get("numero", 0)))
                    except (OSError, ValueError):
                        pass
    return n + 1


def guardar_candidata(d, res, ultima_vela=None):
    import alertas
    from i18n import num, t
    os.makedirs(CARPETA, exist_ok=True)
    nro = _numero_siguiente()
    es, en = NOMBRE_DISPARO.get(d["_tipo"], ("Estrategia", "Strategy"))
    f = firma(d)
    out = {k: v for k, v in d.items() if not k.startswith("_")}
    out.update(id=f"LAB_{f}", numero=nro, nombre=f"Lab {nro}: {es}", nombre_en=f"Lab {nro}: {en}", _firma=f,
               _familia=familia(d),
               creada=datetime.now().strftime("%Y-%m-%d %H:%M"), descubierta=time.time(), origen="laboratorio",
               examen=True, estado="observacion", observacion=dict(desde=ultima_vela, dias=OBSERVACION_DIAS),
               validacion=dict(
                   entreno=dict(desde=DESDE, hasta=CORTE, ops=len(res["entreno"]), pf=round(pf(res["entreno"]), 3),
                                resultado=round(sum(res["entreno"]), 2)),
                   prueba=dict(desde=CORTE, examen=True, ops=len(res["prueba"]), pf=round(pf(res["prueba"]), 3),
                               resultado=round(sum(res["prueba"]), 2)),
                   por_moneda={a: dict(ops=m["ops"], resultado=round(m["resultado"], 2))
                               for a, m in res["por_moneda"].items()},
                   por_anio={str(k): round(v, 2) for k, v in sorted(res["por_anio"].items())},
                   semestres_prueba=[round(x, 2) for x in semestres_prueba(res)[0]]))
    problemas = R.validar(out)
    if problemas:
        raise ValueError(problemas)
    with open(os.path.join(CARPETA, out["id"] + ".json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    v = out["validacion"]["prueba"]
    alertas.agregar(f"candidata_{out['id']}", "candidata", t("Nueva estrategia en observación: {e}", e=out["nombre"]), t(
        "Aprobó el examen final: en los últimos 12 meses, que no miró al buscarla, ganó {pf} veces lo que perdió en {n} "
        "operaciones. Ahora queda 3 meses en observación, sin dinero: si le va al menos tan bien como Breakout y Resorte "
        "de tendencia, entra sola al piloto automático. Mirala en Estrategias → Laboratorio.", pf=num(v["pf"]),
        n=v["ops"]), {"estrategia": out["id"]})
    return out


def _corte_dinamico(Ds):
    ult = max(D["T"][-1] for D in Ds.values())
    return datetime.fromtimestamp((ult - 365 * 86400000) / 1000, timezone.utc).strftime("%Y-%m-%d")


def _rendimiento(estr, Ds, desde_ms):
    """Resultado (en %) de una estrategia desde desde_ms hasta la última vela, promedio de las monedas, con las mismas
    comisiones del laboratorio. Corre desde 2022 para que la estrategia llegue con sus posiciones como en la realidad."""
    inicio, vals = _ms(DESDE), []
    for D in Ds.values():
        sl = E.Sleeve(estr, RIESGO, APAL, COMISION, 0.0, 100.0)
        base = None
        for i in range(1, D["n"]):
            if D["T"][i] < inicio:
                continue
            sl.on_bar(D, i); sl.closed = []
            if base is None and D["T"][i] >= desde_ms:
                base = sl.mark(D["C"][i])
        if base:
            vals.append(sl.mark(D["C"][-1]) / base - 1)
    return sum(vals) / len(vals) * 100 if vals else None


def _mover(nombre_archivo, sub):
    os.makedirs(os.path.join(CARPETA, sub), exist_ok=True)
    os.replace(os.path.join(CARPETA, nombre_archivo), os.path.join(CARPETA, sub, nombre_archivo))


def revisar_observacion(Ds, log=print, ahora_ms=None):
    """Actualiza las candidatas en observación y decide las que cumplieron los 3 meses. Devuelve (ascendidas, descartadas)."""
    import alertas
    import archivos
    from i18n import num, t
    ascendidas, descartadas = [], []
    if not os.path.isdir(CARPETA):
        return ascendidas, descartadas
    ult = max(D["T"][-1] for D in Ds.values())
    ahora_ms = ahora_ms or ult
    for fn in sorted(os.listdir(CARPETA)):
        if not (fn.startswith("LAB_") and fn.endswith(".json")):
            continue
        p = os.path.join(CARPETA, fn)
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            continue
        if not d.get("examen"):  # candidata del laboratorio anterior (sin examen final): se descarta sin aviso
            _mover(fn, "descartadas")
            continue
        if d.get("estado") != "observacion":
            continue
        ob = d.setdefault("observacion", {})
        desde = ob.get("desde") or ult
        E.STRATS["_OBS"] = R.compilar(d)
        try:
            rc = _rendimiento("_OBS", Ds, desde)
        finally:
            E.STRATS.pop("_OBS", None)
        rb_l = [_rendimiento(s, Ds, desde) for s in K.PILOTO_BASE if s in E.STRATS]
        rb = sum(rb_l) / len(rb_l) if rb_l else None
        ob.update(ella=None if rc is None else round(rc, 2), base=None if rb is None else round(rb, 2),
                  actualizado=time.time())
        termino = ahora_ms - desde >= ob.get("dias", OBSERVACION_DIAS) * 86400000
        if termino and rc is not None and rb is not None:
            nombre = d.get("nombre", d["id"])
            if rc > 0 and rc >= rb:
                d["estado"] = "piloto"; d["piloto_desde"] = time.time()
                import catalogo
                catalogo.guardar_propia(d)
                aj = archivos.leer_json("ajustes.json", {}) or {}
                extra = [x for x in aj.get("piloto_extra", []) if x != d["id"]] + [d["id"]]
                aj["piloto_extra"] = extra
                archivos.escribir_json("ajustes.json", aj)
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=1)
                _mover(fn, "ascendidas")
                ascendidas.append(d["id"])
                alertas.agregar(f"asciende_{d['id']}", "recupera", t("{e} entra al piloto automático", e=nombre), t(
                    "Terminó los 3 meses de observación: ganó {a} contra {b} de Breakout y Resorte de tendencia en el mismo "
                    "período. Desde ahora el piloto le da una parte igual que a ellas. La app se reinicia sola para "
                    "sumarla.", a=num(rc, 1, True) + " %", b=num(rb, 1, True) + " %"), {"estrategia": d["id"]})
                log(f"{d['id']} asciende al piloto ({rc:.1f} % contra {rb:.1f} %)")
            else:
                d["estado"] = "descartada"
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=1)
                _mover(fn, "descartadas")
                descartadas.append(d["id"])
                alertas.agregar(f"descarta_{d['id']}", "info", t("{e} se descartó", e=nombre), t(
                    "Terminó los 3 meses de observación: {a} contra {b} de Breakout y Resorte de tendencia en el mismo "
                    "período. Para entrar al piloto tenía que ganar y que le fuera al menos tan bien como ellas. No usó "
                    "dinero en ningún momento.", a=num(rc, 1, True) + " %", b=num(rb, 1, True) + " %"),
                    {"estrategia": d["id"]})
                log(f"{d['id']} descartada ({rc:.1f} % contra {rb:.1f} %)")
        else:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
    return ascendidas, descartadas


def correr(minutos, semilla=None, Ds=None, log=print):
    global CORTE
    rng = random.Random(semilla)
    inicio = time.time()
    st = _estado(corriendo=True, pid=os.getpid(), inicio=inicio, latido=inicio, probadas=0, mensaje="preparando datos")
    if Ds is None:
        Ds = {}
        for a, sym in K.SYMBOLS.items():
            Ds[a] = R.completar(E.prepare(velas(a, sym, log), K.BAR_MS, K.HTF_MS))
    CORTE = CORTE or _corte_dinamico(Ds)
    ultima_vela = max(D["T"][-1] for D in Ds.values())
    _estado(mensaje="revisando las candidatas en observación")
    ascendidas, descartadas = revisar_observacion(Ds, log)
    ya = _firmas_existentes()
    for s in E.STRATS.values():  # las del catálogo también cuentan como existentes
        if "datos" in s:
            ya.add(firma(dict(s["datos"], salida=s["datos"].get("salida", []))))
    poblacion, probadas, vistos = [], 0, set()
    fin = inicio + minutos * 60
    _estado(mensaje="buscando")
    while time.time() < fin:
        d = mutar(rng.choice(poblacion)[1], rng) if poblacion and rng.random() < 0.6 else nueva(rng)
        f = firma(d)
        if f in vistos or f in ya:
            continue
        vistos.add(f)
        res = evaluar(d, Ds)
        probadas += 1
        sc = puntaje(res, d)
        if sc > 0:
            poblacion.append((sc, d, res))
            poblacion.sort(key=lambda x: -x[0])
            del poblacion[20:]
        if probadas % 20 == 0:
            _estado(latido=time.time(), probadas=probadas, mensaje="buscando")
    # prueba fuera de muestra, solo para las finalistas
    nuevas, rechazos = [], {}
    finalistas, fams = [], set()
    for p in poblacion:  # una por familia: no propone cinco variantes de la misma idea
        if pf(p[2]["entreno"]) >= PF_ENTRENO and familia(p[1]) not in fams and "fam:" + familia(p[1]) not in ya:
            finalistas.append(p); fams.add(familia(p[1]))
        if len(finalistas) >= FINALISTAS:
            break
    for _, d, res in finalistas:
        ya.add(firma(d))
        ok, motivos = aprueba(res)
        if ok and len(nuevas) < MAX_NUEVAS:
            nuevas.append(guardar_candidata(d, res, ultima_vela))
            ya.add("fam:" + familia(d))
        else:
            for m in motivos:
                rechazos[m] = rechazos.get(m, 0) + 1
    _guardar_probadas(ya)
    anterior = st.get("probadas_total", 0)
    _estado(corriendo=False, fin=time.time(), latido=time.time(), probadas=probadas, probadas_total=anterior + probadas,
            finalistas=len(finalistas), nuevas=[n["id"] for n in nuevas], rechazos=rechazos,
            candidatas_total=st.get("candidatas_total", 0) + len(nuevas), ascendidas=ascendidas,
            descartadas=descartadas, corte=CORTE, mensaje="listo")
    return nuevas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutos", type=float, default=30)
    ap.add_argument("--semilla", type=int, default=None)
    a = ap.parse_args()
    try:
        import json as _j
        with open("ajustes.json", encoding="utf-8") as f:
            import i18n
            i18n.set_lang(_j.load(f).get("idioma", "es"))
    except (OSError, ValueError):
        pass
    try:
        if os.name == "nt":  # prioridad baja: la app y el bot siempre van primero
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
        correr(a.minutos, a.semilla)
    except Exception as e:
        _estado(corriendo=False, fin=time.time(), mensaje=f"error: {type(e).__name__}: {e}"[:300])
        raise


if __name__ == "__main__":
    main()
