@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ==========================================================
echo   Instalacion del sistema de transcripcion (una sola vez)
echo ==========================================================
echo.

set "PY="
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [ERROR] No encontre Python.
  echo Instala Python 3.12 desde https://www.python.org/downloads/
  echo y marca la casilla "Add python.exe to PATH". Despues volve a abrir este archivo.
  pause
  exit /b 1
)
echo Usando: %PY%

if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  %PY% -m venv .venv
  if errorlevel 1 ( echo [ERROR] No se pudo crear el entorno. & pause & exit /b 1 )
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
echo.
echo Instalando Whisper y librerias de la GPU (puede tardar varios minutos)...
python -m pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] Fallo la instalacion de librerias. & pause & exit /b 1 )

echo.
echo Descargando el modelo (~3 GB, solo la primera vez) y probando la GPU...
set PYTHONIOENCODING=utf-8
python herramientas\fase1_transcribir.py --verificar
echo.
pause
