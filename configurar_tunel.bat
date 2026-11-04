@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist ".venv\Scripts\python.exe" (
  echo Primero tenes que ejecutar instalar.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" scripts\configurar_tunel.py
pause
