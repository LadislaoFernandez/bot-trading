# Bot de trading

Bot de trading para **Binance Futuros (USDⓈ-M)** con aplicación de escritorio para Windows. Opera BTC, ETH y SOL en velas de 1 hora con seis estrategias (Breakout, Resorte de tendencia, Reversión a la media, RSI(2), Cruce de medias y Supertrend), que se activan a mano o deja que el bot las elija solo según el tipo de mercado.

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
| Dinero real | Órdenes en tu cuenta. Hay que escribir REAL para activarlo. |

Las claves de API quedan cifradas en la PC (Windows DPAPI). Para el modo real usá una clave **sin permiso de retiros** y restringida a tu IP.

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
| `auto.py` | Modo automático: elige estrategias según el mercado |
| `mercado.py` | Lectura del mercado e historial por tipo de mercado |
| `actualizador.py` | Actualizaciones desde GitHub Releases |
| `installer/` | Instalador para Windows |
