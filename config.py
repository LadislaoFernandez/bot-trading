"""Configuración del bot v2: portafolio Breakout + Resorte de tendencia en 1h."""

SYMBOLS = {"BTC": "BTC/USDT:USDT", "ETH": "ETH/USDT:USDT", "SOL": "SOL/USDT:USDT"}
STRATEGIES = ["BREAKOUT", "TL"]          # cada estrategia x cada activo = 6 posiciones independientes
PILOTO_BASE = ["BREAKOUT", "TL"]         # las que usa el piloto automático (ver auto.py)
RETIRADAS = ["MR", "RSI2", "CRUCE", "SUPERTREND"]  # no suman a Breakout y Resorte: no se ofrecen (sus posiciones abiertas se cierran normalmente)

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
VERSION = "1.32"
REPO = "LadislaoFernandez/bot-trading"  # de acá salen las actualizaciones (GitHub Releases)
HISTORIAL_VERSIONES = [
    ("1.32", "13/11/2026", [
        "App de Android: ruedita de carga arriba mientras trae los datos (al abrir la app, al volver a ella y al "
        "actualizar), y \"tirar para actualizar\": arrastrando la pantalla hacia abajo estando arriba de todo se "
        "actualiza al instante, en cualquier pantalla.",
        "App de Android: al volver a la app pide los datos en el momento, en lugar de mostrar los de cuando se cerró.",
        "App de Android: espera a que el APK nuevo esté subido antes de bajarlo (antes podía mostrar \"HTTP Error 404\" "
        "durante la publicación).",
    ]),
    ("1.31", "13/11/2026", [
        "El stop se ajusta cada 10 minutos (antes solo al cierre de cada vela de 1 hora), con las mismas reglas: lo "
        "sigue a 3 ATR del precio, pasa a la entrada más comisiones con 2 ATR de ganancia y nunca retrocede. En Binance "
        "primero pone el stop nuevo y después cancela el viejo. Las entradas y salidas siguen en velas de 1 hora.",
    ]),
    ("1.30", "11/11/2026", [
        "Las versiones nuevas se detectan mucho más rápido: el servidor y la app de Windows buscan cada 2 minutos (antes "
        "cada hora), y la app de Android le pregunta directo a GitHub al abrirse, sin esperar al servidor.",
    ]),
    ("1.29", "11/11/2026", [
        "Diseño nuevo en las dos apps: fondo azul noche (o modo claro), tarjetas con borde y franja de color, títulos de "
        "sección y cuadritos para los números. Se elige oscuro o claro en Configuración.",
        "App de Android: las pestañas pasan a un menú lateral (botón ☰ arriba a la izquierda) en lugar de la barra de abajo.",
        "La pestaña Servidor se llama ahora Configuración.",
    ]),
    ("1.28", "11/11/2026", [
        "App de Android: se actualiza sola desde la app (baja e instala la versión nueva; la primera vez Android pide "
        "confirmar, después ya no). Al refrescar los datos la pantalla ya no vuelve arriba.",
    ]),
    ("1.27", "11/11/2026", [
        "Textos de Posiciones y de las estrategias actualizados: explican el stop inicial a 2 ATR, el stop móvil a 3 ATR "
        "y el paso a la entrada con 2 ATR de ganancia.",
    ]),
    ("1.26", "10/11/2026", [
        "Breakout y Resorte de tendencia aseguran la operación: cuando lleva 2 ATR de ganancia, el stop pasa a la "
        "entrada más las comisiones y ya no puede cerrar en pérdida (simulado 2022-2026: Breakout de 250 a 281 por "
        "cada 100). Cruce y Supertrend siguen igual, porque ahí empeoraba.",
    ]),
    ("1.25", "10/11/2026", [
        "Botón Copiar código de conexión (Windows y Android, en Servidor) para conectar otra app o un celular nuevo al "
        "mismo servidor. El instalador de Windows también se publica como BotTrading-Setup.exe (link fijo).",
    ]),
    ("1.24", "10/11/2026", [
        "App de Android: crear el servidor en Oracle desde el celular (mismo asistente que en Windows) y conectar "
        "Binance demo o real desde la pestaña Servidor, sin comandos.",
        "Conectar Binance: textos corregidos (la opción se llama Autogenerada; en la demo los permisos ya vienen listos y "
        "la restricción de IP no hace falta; en la cuenta real se configura en Editar restricciones).",
    ]),
    ("1.23", "10/11/2026", [
        "Asistente de Oracle: si Oracle no tiene lugar para máquinas gratis, reintenta solo cada minuto (hasta 2 horas) "
        "en lugar de fallar.",
    ]),
    ("1.22", "10/11/2026", [
        "Control de Windows: asistente que crea el servidor gratis en Oracle Cloud con un botón (red, puerto, máquina "
        "Always Free e instalación del bot), sin comandos ni SSH. Solo hace falta la cuenta de Oracle y una clave de API "
        "que genera la app.",
        "Servidor → Cuenta de Binance: conectar Binance demo o real y cambiar de modo desde la app. El servidor genera "
        "la clave y la parte privada nunca sale de él.",
        "Avisos al celular para cualquier servidor: los que no tienen Firebase los mandan por el servidor del dueño de "
        "la app.",
    ]),
    ("1.21", "10/11/2026", [
        "App de Android con los cambios de la 1.20 (precio actual y resultado si toca el stop en Posiciones).",
        "Servidor: al reiniciar con posiciones abiertas ya no muestra el aviso de Binance -4067 (no se puede cambiar el "
        "modo con órdenes abiertas), que era inofensivo.",
    ]),
    ("1.20", "10/11/2026", [
        "Posiciones: precio actual de cada posición abierta y cuánto ganaría o perdería si toca el stop (las estrategias "
        "no tienen precio objetivo fijo: usan stop móvil).",
    ]),
    ("1.19", "10/11/2026", [
        "Control de Windows y app de Android: precio actual de BTC, ETH y SOL y su cambio en 24 horas en Resumen.",
    ]),
    ("1.18", "10/11/2026", [
        "Avisos al celular por Firebase Cloud Messaging (como Instagram): el servidor los manda y llegan aunque la app "
        "esté cerrada y la pantalla apagada, sin ajustes de batería. La app ya no deja un servicio corriendo.",
        "Servidor: comando probar_push para probar los avisos.",
    ]),
    ("1.17", "09/11/2026", [
        "Control de Windows y app de Android: pestaña Decisiones, con lo que miró el bot en cada revisión para cada "
        "estrategia en cada moneda (qué condiciones se cumplen y cuáles faltan para abrir).",
    ]),
    ("1.16", "09/11/2026", [
        "App de Android: pestañas Estrategias (piloto automático, capital mínimo y resultados de cada estrategia por año "
        "y semestre) y Servidor (conexión, riesgo, capital, laboratorio y actualizaciones del servidor), como en Windows. "
        "La barra de pestañas se desliza de costado.",
        "Control de Windows: el interruptor \"Instalar solas\" muestra el valor real del servidor.",
    ]),
    ("1.15", "09/11/2026", [
        "App de Android: todas las versiones se firman con la misma llave, así se instalan encima de la anterior "
        "(antes Android decía que había un conflicto con el paquete). Hace falta desinstalar una sola vez la app vieja.",
    ]),
    ("1.14", "09/11/2026", [
        "App de Android: botón Pegar en la pantalla del código de conexión (en algunos celulares, mantener apretado el "
        "campo no muestra la opción de pegar).",
    ]),
    ("1.13", "09/11/2026", [
        "Control remoto de Windows: se actualiza solo (busca versiones nuevas al abrirse y cada hora, las instala y se "
        "reinicia).",
        "App de Android: avisa cuando hay una versión nueva (en Resumen y con una notificación) y la baja con un toque.",
        "Windows: el instalador ya no instala la app de escritorio vieja (sin acceso directo ni inicio automático) y el "
        "control remoto borra lo que quedaba de ella: inicio automático, accesos directos, datos locales y lanzadores.",
    ]),
    ("1.12", "09/11/2026", [
        "App de Android: notificación en el celular cada vez que el bot abre o cierra una operación, aunque la app esté "
        "cerrada (se enciende y apaga en Control → Notificaciones).",
        "Servidor: nueva consulta de eventos (aperturas y cierres) para los avisos del celular.",
    ]),
    ("1.11", "08/11/2026", [
        "Bot en la nube: el bot puede correr en un servidor gratis de Oracle Cloud las 24 horas, sin depender de la PC. "
        "Guía paso a paso en SERVIDOR.md e instalación con un solo comando.",
        "Apps de control remoto para Windows y Android: se conectan al servidor con un código de conexión (HTTPS con el "
        "certificado del servidor fijado) y muestran resumen, posiciones, operaciones, estrategias, avisos y registro. "
        "Permiten prender o apagar el bot, el piloto y el laboratorio, revisar ahora, reanudar y cambiar riesgo y capital.",
        "Capital mínimo recomendado más claro: dice el total, cuántas partes y cuánto por parte, y aparece también en "
        "Configuración junto al capital.",
    ]),
    ("1.10.1", "07/11/2026", [
        "Inicio con Windows: la app arranca directamente con el Python que trae el instalador. Antes, sin un Python "
        "instalado en el sistema, se abría la carpeta del bot en vez de la app.",
    ]),
    ("1.10", "07/11/2026", [
        "Laboratorio nuevo: busca una vez por semana solo con datos hasta hace 12 meses; las 5 mejores rinden un examen "
        "final con los últimos 12 meses, una sola vez cada una.",
        "La que aprueba queda 3 meses en observación sin dinero. Si gana y le va al menos tan bien como Breakout y "
        "Resorte de tendencia, entra sola al piloto automático con una parte igual; si no, se descarta. Avisa en los dos "
        "casos.",
        "Se retiraron Cruce de medias y Supertrend (no le sumaban a Breakout y Resorte), y las estrategias del "
        "laboratorio anterior pasaron a respaldos/estrategias_viejas.",
    ]),
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
