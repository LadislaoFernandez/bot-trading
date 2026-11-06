@echo off
rem Abre la aplicacion del bot. Con --minimizado arranca oculta, en el icono junto a la hora.
cd /d "%~dp0"
call _buscar_python.bat
%PY% -c "import PySide6.QtWidgets, ccxt" >nul 2>nul || %PY% -m pip install -q -r requirements.txt
for /f "delims=" %%i in ('%PY% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set PYW=%%i
start "" "%PYW%" app.py %*
