# Bot de trading

Bot de trading para **Binance Futuros (USDⓈ-M)** con aplicación de escritorio para Windows. Opera BTC, ETH y SOL en velas de 1 hora. Con el **piloto automático** usa Breakout y Resorte de tendencia en las tres monedas, reparte todo el capital en partes iguales una vez por día y revisa una vez por mes que cada estrategia siga ganando. Con el piloto apagado se eligen a mano estrategias (también Cruce de medias, Supertrend y las del laboratorio) y montos. Un laboratorio busca estrategias nuevas en segundo plano y propone las que pasan una prueba con datos que no usó para crearlas.

En simulaciones con el código del bot, de enero 2023 a octubre 2026 y con 300 USDT, el piloto terminó en unos 1.500 USDT con comisión de orden límite y en unos 740 USDT con comisión a mercado; la caída máxima fue de 28 % a 36 %.

> Operar con apalancamiento es riesgoso y podés perder dinero. Los resultados pasados no garantizan resultados futuros. Probalo primero en modo simulado y en la demo de Binance.

## Instalar

1. Bajá **`BotTrading-Setup-X.Y.exe`** de la [última versión](https://github.com/LadislaoFernandez/bot-trading/releases/latest).
2. Abrilo y seguí los pasos. Trae todo lo necesario (incluido Python): no hace falta instalar nada más.
3. Abrí **Bot de trading** desde el menú Inicio. En **Configuración → Primeros pasos** está la guía para conectarlo a Binance.

La app se actualiza sola: busca versiones nuevas al iniciar y muestra un aviso abajo a la izquierda para instalarlas.

## Modos

| Modo | Qué hace |
|---|---|
| Simulado | Precios reales de Binance, órdenes simuladas. No necesita claves. |
| Demo de Binance | Órdenes reales en *Trading de prueba* de Binance, con dinero de prueba. |
| Dinero real | Órdenes en tu cuenta. Antes de activarlo la app muestra una lista de control y hay que escribir REAL. |

Las claves de API quedan cifradas en la PC (Windows DPAPI). Para el modo real la clave tiene que tener futuros habilitados, **retiros deshabilitados** y restricción de IP: la app lo verifica al probar la conexión y no deja pasar a dinero real si falta algo.

## Para desarrollar

```
pip install -r requirements.txt
python app.py --prueba          # solo la ventana, sin arrancar el bot
python tests/correr_pruebas.py  # pruebas (sin internet)
python backtest.py --desde 2026-01-01 --hasta 2026-11-01
```

### Publicar una versión

1. Subí `VERSION` en `config.py` y agregá la entrada en `HISTORIAL_VERSIONES` (es el texto de la publicación).
2. `git tag vX.Y && git push origin main vX.Y`, o en GitHub: Actions → Publicar versión → Run workflow con "publicar" tildado.
3. GitHub Actions corre las pruebas, arma `actualizacion.zip` y el instalador `.exe` (Inno Setup, con Python 3.12 incluido) y publica la versión. Las apps instaladas la ven en la próxima búsqueda.

| Archivo | Para qué |
|---|---|
| `app.py` | Aplicación de escritorio (PySide6) con el bot adentro |
| `engine.py` | Indicadores y reglas de cada estrategia |
| `paper_trader.py` / `live.py` | El bot: modo simulado / órdenes en Binance |
| `auto.py` | Piloto automático: estrategias base, reequilibrio diario en partes iguales y revisión mensual |
| `reglas.py` / `catalogo.py` | Estrategias definidas como datos (JSON) y su catálogo (`estrategias/`, `mis_estrategias/`) |
| `laboratorio.py` | Laboratorio: busca estrategias nuevas y propone las que pasan la prueba fuera de muestra |
| `alertas.py` | Avisos de la app (revisión mensual del piloto, candidatas nuevas) |
| `mercado.py` | Lectura del mercado e historial de cada estrategia (por año, mes y semestre) |
| `actualizador.py` | Actualizaciones desde GitHub Releases |
| `installer/` | Instalador para Windows |
