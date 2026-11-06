rem Busca Python: primero el que trae el instalador (carpeta python), despues el del sistema
set PY=
if exist "%~dp0python\python.exe" set PY="%~dp0python\python.exe"
if defined PY goto :eof
python -c "import sys" >nul 2>nul && set PY=python
if defined PY goto :eof
py -3 -c "import sys" >nul 2>nul && set PY=py -3
if defined PY goto :eof
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
goto :eof
