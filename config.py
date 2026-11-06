"""Configuración del bot v2: portafolio Breakout + Resorte de tendencia en 1h."""

SYMBOLS = {"BTC": "BTC/USDT:USDT", "ETH": "ETH/USDT:USDT", "SOL": "SOL/USDT:USDT"}
STRATEGIES = ["BREAKOUT", "TL"]          # cada estrategia x cada activo = 6 posiciones independientes

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
LIMITE_PERDIDA = 0.25         # si la cuenta del bot cae 25 % desde su capital inicial, deja de abrir operaciones

# ------------------------------------------------------------------ versiones de la aplicación
VERSION = "1.5"
REPO = "LadislaoFernandez/bot-trading"  # de acá salen las actualizaciones (GitHub Releases)
HISTORIAL_VERSIONES = [
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
