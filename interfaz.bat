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
python -c "import docx" 2>nul || python -m pip install -q python-docx
python servidor.py
pause
