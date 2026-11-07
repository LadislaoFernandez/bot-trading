@echo off
rem Abre la aplicacion del bot. Con --minimizado arranca oculta, en el icono junto a la hora.
cd /d "%~dp0"
if exist "%~dp0python\pythonw.exe" (
    start "" "%~dp0python\pythonw.exe" "%~dp0app.py" %*
    goto :eof
)
call _buscar_python.bat
if not defined PY (
    echo No se encontro Python. Reinstala la aplicacion con el instalador.
    pause
    goto :eof
)
%PY% -c "import PySide6.QtWidgets, ccxt" >nul 2>nul || %PY% -m pip install -q -r requirements.txt
set PYW=
rem "call" evita que cmd le saque las comillas a una ruta con espacios
for /f "delims=" %%i in ('call %PY% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set PYW=%%i
if not defined PYW (
    echo No se pudo encontrar pythonw.exe.
    pause
    goto :eof
)
start "" "%PYW%" "%~dp0app.py" %*
