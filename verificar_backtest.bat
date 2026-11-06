@echo off
title Verificacion backtest 2026
cd /d "%~dp0"
call _buscar_python.bat
%PY% backtest.py --desde 2026-01-01 --hasta 2026-11-01 > backtest_2026.txt 2>&1
echo LISTO >> backtest_2026.txt
