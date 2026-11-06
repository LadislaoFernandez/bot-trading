@echo off
rem Cierra la app que esta corriendo y la vuelve a abrir (el estado del bot se conserva)
cd /d "%~dp0"
echo INICIO > actualizacion.txt
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; 'DETENIDO ' + $_.ProcessId }" >> actualizacion.txt 2>&1
timeout /t 2 /nobreak >nul
call iniciar_bot.bat
echo APP_INICIADA >> actualizacion.txt
