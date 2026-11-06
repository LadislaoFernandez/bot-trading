@echo off
title Estado del bot
cd /d "%~dp0"
call _buscar_python.bat
%PY% paper_trader.py --estado
pause
