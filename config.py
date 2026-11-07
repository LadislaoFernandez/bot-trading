"""Configuración del bot v2: portafolio Breakout + Resorte de tendencia en 1h."""

SYMBOLS = {"BTC": "BTC/USDT:USDT", "ETH": "ETH/USDT:USDT", "SOL": "SOL/USDT:USDT"}
STRATEGIES = ["BREAKOUT", "TL"]          # cada estrategia x cada activo = 6 posiciones independientes
PILOTO_BASE = ["BREAKOUT", "TL"]         # las que usa el piloto automático (ver auto.py)
RETIRADAS = ["MR", "RSI2"]               # perdieron todos los años desde 2023: no se ofrecen (sus posiciones abiertas se cierran normalmente)

TIMEFRAME = "1h"
BAR_MS = 3_600_000
HTF_MS = 4 * BAR_MS                      # tendencia EMA10/55 en velas de 4h (usada por TL)

INITIAL_CAPITAL = 100.0                  # USDT totales, repartidos en partes iguales entre las 6 posiciones
RISK_PER_TRADE = 0.03                    # 3% del capital de cada posición arriesgado hasta el stop
MAX_LEVERAGE = 10.0                      # tope de nocional / capital de cada posición
FEE = 0.0002                             # comisión maker Binance Futuros (orden límite)
SLIPPAGE = 0.0                           # con orden límite no hay slippage (supone que se llena)

STATE_FILE = "estado_bot.json"
TRADES_FILE = "operaciones.csv"
EQUITY_FILE = "capital_horario.csv"
LOG_FILE = "bot.log"
DECISIONES_FILE = "decisiones.jsonl"

# ------------------------------------------------------------------ modos de operación
MODO = "simulado"   # simulado | demo | real (lo cambia la aplicación)
ARCHIVOS_MODO = {
    "simulado": dict(STATE_FILE="estado_bot.json", TRADES_FILE="operaciones.csv", EQUITY_FILE="capital_horario.csv",
                     LOG_FILE="bot.log", DECISIONES_FILE="decisiones.jsonl"),
    "demo": dict(STATE_FILE="estado_demo.json", TRADES_FILE="operaciones_demo.csv", EQUITY_FILE="capital_demo.csv",
                 LOG_FILE="bot_demo.log", DECISIONES_FILE="decisiones_demo.jsonl"),
    "real": dict(STATE_FILE="estado_real.json", TRADES_FILE="operaciones_real.csv", EQUITY_FILE="capital_real.csv",
                 LOG_FILE="bot_real.log", DECISIONES_FILE="decisiones_real.jsonl"),
}
NOMBRE_MODO = {"simulado": "Simulado", "demo": "Demo de Binance", "real": "Dinero real"}
FEE_TAKER = 0.0005            # comisión a mercado en Binance Futuros
ESPERA_ORDEN_LIMITE = 180     # segundos que espera una orden límite antes de completar a mercado
OBSOLETOS = ["ver_estado.bat", "verificar_backtest.bat", "actualizar_app.bat"]  # de versiones viejas: la app los borra al abrir
LIMITE_PERDIDA = 0.25         # si la cuenta del bot cae 25 % desde su capital inicial, deja de abrir operaciones

# ------------------------------------------------------------------ versiones de la aplicación
VERSION = "1.9.2"
REPO = "LadislaoFernandez/bot-trading"  # de acá salen las actualizaciones (GitHub Releases)
HISTORIAL_VERSIONES = [
    ("1.9.2", "07/11/2026", [
        "Resultados por mes: un cambio de capital que vuelve atrás (por ejemplo de 300 a 350 y de nuevo a 300) ya no "
        "aparece como pérdida.",
    ]),
    ("1.9.1", "07/11/2026", [
        "Resultados por mes y caída máxima: los cambios de capital del modo ya no cuentan como ganancia o pérdida.",
    ]),
    ("1.9", "07/11/2026", [
        "Piloto automático nuevo: usa Breakout y Resorte de tendencia en BTC, ETH y SOL, prendidas todo el tiempo, y "
        "reparte todo el capital en partes iguales una vez por día. Ya no cambia de estrategia según el tipo de mercado "
        "(en las simulaciones de 2023 a 2026 eso perdía contra dejarlas fijas).",
        "Revisión mensual: si una estrategia del piloto pierde plata en los últimos 12 meses en 3 revisiones seguidas, "
        "deja de recibir dinero y la app avisa. Vuelve sola si pasa 3 revisiones seguidas.",
        "Estrategias: cada tarjeta muestra el resultado por año y por semestre. Se retiraron Reversión a la media y "
        "RSI(2), que perdieron todos los años desde 2023, y la recomendación por tipo de mercado.",
        "Resumen: resultados por mes comparados con la simulación, caída máxima, y órdenes y comisiones (cuántas se "
        "completaron a mercado).",
        "Capital mínimo recomendado para que todas las partes lleguen al mínimo de Binance.",
        "Dinero real: la app verifica los permisos de la clave (futuros sí, retiros no, IP restringida) y muestra una "
        "lista de control antes de activarlo.",
        "Laboratorio más exigente: las candidatas tienen que ganar en casi todos los semestres de la prueba y en los "
        "últimos 12 meses. Se sacó \"Proponer para todos\".",
        "Se borran archivos de versiones viejas que ya no se usaban.",
    ]),
    ("1.8.1", "06/11/2026", [
        "Piloto automático sin tope de estrategias por moneda: cada estrategia que conviene se usa en todas las monedas "
        "donde convenga (antes, como mucho 2 por moneda).",
        "La rueda del mouse ya no cambia montos ni listas desplegables sin querer: sigue desplazando la página.",
    ]),
    ("1.8", "06/11/2026", [
        "Piloto automático: prende y apaga las estrategias según el mercado de cada moneda y reparte todo el capital, "
        "incluidas las ganancias, dando más a las que mejor funcionan (tope 40 % por parte) y respetando el mínimo de "
        "Binance.",
        "La sección \"Cómo se eligen las estrategias\" pasa a llamarse \"Piloto automático\"; el resumen muestra cuánto "
        "recibe cada parte.",
    ]),
    ("1.7.1", "06/11/2026", [
        "Al activar una estrategia sin capital sin asignar, la app avisa y ofrece repartir todo como recomienda el bot o "
        "asignarle el monto a mano.",
    ]),
    ("1.7", "06/11/2026", [
        "Botón Guardar y repartir como recomienda el bot, en Configuración: reparte el capital entre las estrategias "
        "activas de cada moneda según cómo funcionaron en el tipo de mercado de hoy, sin pasar del 40 % en ninguna y "
        "respetando el mínimo de Binance.",
    ]),
    ("1.6.6", "06/11/2026", [
        "Mínimos de Binance en los montos: la app lee de Binance el tamaño mínimo por orden de cada moneda, calcula con "
        "la volatilidad de hoy cuánto necesita cada estrategia para llegar a ese mínimo y marca en rojo los montos que "
        "no llegan.",
    ]),
    ("1.6.5", "06/11/2026", [
        "Al bajar el capital, la cuenta de cuánto bajar los montos usa los montos guardados y no los que el bot todavía "
        "no aplicó (antes se podían bajar dos veces).",
    ]),
    ("1.6.4", "06/11/2026", [
        "Modo automático: reparte todo el capital (el del modo más lo que vaya ganando) en partes iguales entre las "
        "estrategias que elige en las tres monedas. Ya no hay que elegir dinero por moneda.",
        "Al repartir montos, primero se bajan las partes que liberan capital y después se suben las demás, así no queda "
        "ninguna corta por falta de capital sin asignar.",
    ]),
    ("1.6.3", "06/11/2026", [
        "Al bajar el capital de un modo por debajo de lo asignado a las estrategias, la app avisa y ofrece bajar los "
        "montos en la misma proporción (antes el cambio quedaba sin aplicar y sin aviso).",
        "Configuración avisa si el capital guardado no coincide con el que está usando el bot.",
    ]),
    ("1.6.2", "06/11/2026", [
        "Los montos de cada estrategia se guardan solos a los 2 segundos de cambiarlos (antes había que tocar Guardar "
        "montos, y si activabas o desactivabas una estrategia antes de guardar, se perdían).",
        "Posiciones muestra todas las estrategias activas, también las que todavía no tienen monto asignado.",
    ]),
    ("1.6.1", "06/11/2026", [
        "Arreglo: en Windows, el laboratorio podía cortarse al guardar su estado mientras la app lo leía. Ahora todos los "
        "archivos se guardan reintentando unos segundos.",
    ]),
    ("1.6", "06/11/2026", [
        "Laboratorio de estrategias: busca estrategias nuevas en segundo plano y propone solo las que pasan una prueba "
        "con datos que no usó para crearlas.",
        "Las candidatas aparecen con un aviso en Estrategias: se pueden agregar a tus estrategias, descartar o proponer "
        "para todos los usuarios (abre una propuesta en GitHub).",
    ]),
    ("1.5", "06/11/2026", [
        "Revalidación semanal: cada estrategia se vuelve a probar con los datos de los últimos 90 días, y la app avisa "
        "cuando una empieza a empeorar o se recupera.",
        "El modo automático deja de usar las estrategias que vienen empeorando hasta que se recuperen.",
        "Estrategias definidas como datos: la app puede recibir estrategias nuevas sin cambiar su código.",
        "Avisos en la sección Estrategias y notificación junto a la hora.",
    ]),
    ("1.4.3", "06/11/2026", [
        "Opción para instalar las actualizaciones automáticamente, sin preguntar.",
        "La app busca actualizaciones cada 1 hora.",
    ]),
    ("1.4.2", "06/11/2026", [
        "El instalador cierra solo la copia del bot de su propia carpeta.",
        "El aviso de actualización muestra los cambios sin el formato de GitHub.",
    ]),
    ("1.4.1", "06/11/2026", [
        "Arreglos de la interfaz: los montos en los campos numéricos se ven bien, casillas con tilde y switches con perilla.",
    ]),
    ("1.4", "06/11/2026", [
        "Modo automático: el bot elige qué estrategias usar en cada moneda según el tipo de mercado.",
        "Actualizaciones desde la app: búsqueda automática al iniciar, aviso abajo a la izquierda e instalación con un clic.",
        "Instalador para Windows que trae todo lo necesario, incluido Python.",
        "Primeros pasos con enlaces directos a Binance y la ubicación correcta de Trading de prueba.",
        "Nuevo nombre y descripción para la estrategia de squeeze y momentum: Resorte de tendencia.",
        "Campos numéricos con botones − y + y desplegables con un diseño nuevo. Cada sección tiene una descripción.",
    ]),
    ("1.3", "06/11/2026", [
        "Nueva sección Configuración: guía de primeros pasos, modo y claves de Binance, capital de cada modo, riesgo, "
        "seguridad e historial de versiones.",
        "Elegís cuánto dinero usa cada estrategia en BTC, ETH y SOL.",
        "Cada estrategia explica si conviene o no activarla en el mercado actual.",
        "Idioma español o inglés, tema oscuro (negro y naranja) o claro (blanco y naranja), notificaciones e inicio con "
        "Windows desde la app.",
        "Revisión general de la interfaz: textos que no se cortan, botones y diálogos en el idioma elegido.",
    ]),
    ("1.2", "06/11/2026", [
        "Conexión a Binance Futuros con switch de tres modos: simulado, cuenta demo de Binance y dinero real.",
        "Claves de API guardadas cifradas en la PC. Stops puestos en Binance, órdenes límite con respaldo a mercado.",
        "Seguridad del modo real: confirmación, límite de pérdida y botón para cerrar todas las posiciones del bot.",
    ]),
    ("1.1", "06/11/2026", [
        "El registro explica en cada revisión por qué el bot abrió o no abrió cada posición.",
        "Nueva sección Estrategias: análisis del mercado en vivo, recomendación según el tipo de mercado "
        "y cuatro estrategias nuevas (Reversión a la media, RSI(2), Cruce de medias, Supertrend) que se activan "
        "con un switch.",
        "Numeración de versiones.",
    ]),
    ("1.0", "06/11/2026", [
        "Aplicación de escritorio con el bot adentro: resumen, posiciones, operaciones, registro y estrategia.",
        "Cuenta regresiva a la próxima revisión, precios en vivo y gráfico de la cuenta.",
        "Ícono junto a la hora e inicio automático con Windows.",
    ]),
]
