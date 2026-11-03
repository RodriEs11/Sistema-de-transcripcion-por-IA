@echo off
chcp 65001 >nul
title Transcripcion - Servidor (no cerrar)
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist ".venv\Scripts\python.exe" (
  echo Primero tenes que ejecutar instalar.bat
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"
set "PATH=%~dp0.venv\Scripts;%PATH%"
python -c "import docx" 2>nul || python -m pip install -q python-docx
python servidor.py
rem REINICIO-DESDE-EL-PANEL: el panel de administracion cierra el servidor con el codigo 75
rem para reiniciarlo, y aca se vuelve a abrir solo en esta misma ventana.
rem (Las lineas de arriba no se tocan: Windows sigue leyendo este archivo mientras el servidor esta abierto.)
:despues_del_servidor
if "%errorlevel%"=="75" goto reiniciar
pause
exit /b
:reiniciar
echo.
echo Reiniciando el servidor...
python servidor.py --sin-navegador
goto despues_del_servidor
