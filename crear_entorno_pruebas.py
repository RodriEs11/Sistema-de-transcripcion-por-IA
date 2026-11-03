"""Crea una copia aislada del sistema para probar ramas experimentales sin tocar la instalación en uso.

Uso (desde la carpeta sistema de la instalación en uso):

    python crear_entorno_pruebas.py                     # rama experimental en ..\\sistema_pruebas
    python crear_entorno_pruebas.py --rama exp/mi-idea  # otra rama
    python crear_entorno_pruebas.py --destino D:\\pruebas --puerto 8875

Qué hace:
- Clona el repositorio en otra carpeta (un repositorio independiente, no un worktree) y deja
  `origin` apuntando a GitHub. No cambia de rama, no hace commits ni modifica ningún archivo de
  la instalación en uso: solo la lee.
- Escribe en la copia un `configuracion.json` propio con `Audios_nuevos` e `Informes` DENTRO de
  la copia. Con la configuración de ejemplo (`..\\Audios_nuevos`) la copia leería los audios de
  producción, porque la carpeta de pruebas queda al lado de `sistema`.
- Copia `conocimiento/` y `modelos/` (si existen) para que las plantillas se puedan modificar sin
  afectar producción. Nunca copia contraseñas (`acceso_remoto.json`), huellas de voz, registros,
  resultados, informes, audios, la cola ni los binarios de la app.
- Genera `iniciar_pruebas.bat` / `iniciar_pruebas.sh`: otro puerto (8865 por defecto), sin túnel,
  modo simulado salvo que se pida `real`, y el Python de la instalación en uso (solo lo ejecuta).
- Prepara la app del trabajo para compilarla y probarla en esta PC: copia las bibliotecas de WebView2 de
  `cliente/` (nunca el .exe ni `conexion.json`) y crea `cliente/perfil_pruebas.txt`. Con ese archivo la app usa
  otra carpeta de datos, otra instancia y otra clave de inicio con Windows: no pisa a la app de producción.

En un entorno ya creado, para preparar solo la app (desde la carpeta del entorno de pruebas):

    python crear_entorno_pruebas.py --preparar-app
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MARCA = ".entorno_pruebas"
PUERTO_PRODUCCION = 8765
COPIAR = ("conocimiento", "modelos")          # se copian si existen; el resto se crea vacío o desde ejemplos
CARPETAS_PROPIAS = ("Audios_nuevos", "Informes")
BIBLIOTECAS_APP = ("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll")
PERFIL_APP = "perfil_pruebas.txt"


class ErrorEntorno(Exception):
    pass


def _git(*args, cwd, comprobar=True):
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if comprobar and r.returncode != 0:
        raise ErrorEntorno(f"git {' '.join(args)} falló: {(r.stderr or r.stdout).strip()}")
    return r


def _python_produccion(origen):
    for rel in (".venv/Scripts/python.exe", ".venv-linux/bin/python", ".venv/bin/python"):
        p = origen / rel
        if p.exists():
            return p
    return Path(sys.executable)


def _rama_valida(rama, cwd):
    if _git("check-ref-format", "--branch", rama, cwd=cwd, comprobar=False).returncode != 0:
        raise ErrorEntorno(f"«{rama}» no es un nombre de rama válido.")


def preparar_config(origen, destino):
    """configuracion.json de la copia: la de producción (o la de ejemplo) con carpetas propias."""
    base = origen / "configuracion.json"
    if not base.exists():
        base = origen / "configuracion.ejemplo.json"
    cfg = json.loads(base.read_text(encoding="utf-8-sig"))
    for clave, carpeta in zip(("carpeta_audios_nuevos", "carpeta_informes"), CARPETAS_PROPIAS):
        cfg[clave] = carpeta                       # relativa a la copia (informe.config la resuelve desde AQUI)
        (destino / carpeta).mkdir(exist_ok=True)
    (destino / "configuracion.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
    return cfg


def escribir_lanzadores(destino, python, puerto):
    tunel = puerto + 1
    bat = f"""@echo off
chcp 65001 >nul
title EXPERIMENTAL - Transcripcion PRUEBAS (puerto {puerto})
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set "PUERTO_INTERFAZ={puerto}"
set "PUERTO_TUNEL={tunel}"
set "SIMULAR_IA=1"
if /i "%~1"=="real" set "SIMULAR_IA="
echo ============================================================
echo   ENTORNO DE PRUEBAS - NO es la instalacion en uso
echo   http://127.0.0.1:{puerto}   (produccion usa {PUERTO_PRODUCCION})
if defined SIMULAR_IA (echo   IA simulada. Para Whisper y Ollama reales: iniciar_pruebas.bat real) else (
  echo   IA REAL: comparte la GPU y Ollama con produccion.
  echo   Usalo solo cuando no haya informes en proceso.
  pause
)
echo ============================================================
"{python}" servidor.py
pause
"""
    sh = f"""#!/usr/bin/env bash
# Entorno de pruebas: NO es la instalación en uso. Uso: ./iniciar_pruebas.sh [real]
cd "$(dirname "$(readlink -f "$0")")" || exit 1
source linux/comun.sh
PY="{python.as_posix()}"
titulo "EXPERIMENTAL - Transcripción PRUEBAS (puerto {puerto})"
export PUERTO_INTERFAZ={puerto} PUERTO_TUNEL={tunel} SIMULAR_IA=1
if [ "${{1:-}}" = "real" ]; then
  unset SIMULAR_IA
  aviso "IA REAL: comparte la GPU y Ollama con producción. Usalo solo sin informes en proceso."
  read -r -p "Enter para seguir, Ctrl+C para cancelar " _
fi
preparar_cuda
ok "Entorno de pruebas en http://127.0.0.1:{puerto} (producción usa {PUERTO_PRODUCCION})"
exec "$PY" servidor.py --sin-navegador
"""
    (destino / "iniciar_pruebas.bat").write_text(bat.replace("\n", "\r\n"), encoding="utf-8")
    p = destino / "iniciar_pruebas.sh"
    p.write_text(sh, encoding="utf-8", newline="\n")
    p.chmod(0o755)


def preparar_app(origen, destino):
    """Deja la app compilable (cliente_codigo/compilar.ps1) y aislada en la copia. Devuelve lo copiado."""
    src, dst = Path(origen) / "cliente", Path(destino) / "cliente"
    dst.mkdir(exist_ok=True)
    copiado = []
    for nombre in BIBLIOTECAS_APP:
        if (src / nombre).is_file():
            shutil.copy2(src / nombre, dst / nombre)
            copiado.append(nombre)
    if (src / "runtimes").is_dir():
        shutil.copytree(src / "runtimes", dst / "runtimes", dirs_exist_ok=True)
        copiado.append("runtimes")
    (dst / PERFIL_APP).write_text(
        "Perfil de pruebas de la app (crear_entorno_pruebas.py). Con este archivo junto a Transcripcion.exe la app\n"
        "usa %LOCALAPPDATA%\\Transcripcion-pruebas, otra instancia y otra clave de inicio con Windows.\n"
        "No se distribuye a las PC del trabajo.\n", encoding="utf-8")
    return copiado


def origen_del_entorno(destino):
    """La instalación en uso desde la que se creó el entorno (anotada en .entorno_pruebas)."""
    marca = Path(destino) / MARCA
    if not marca.exists():
        raise ErrorEntorno(f"{destino} no es un entorno de pruebas (falta {MARCA}).")
    texto = marca.read_text(encoding="utf-8").strip()
    prefijo = "Entorno de pruebas creado desde "
    if not texto.startswith(prefijo):
        raise ErrorEntorno(f"No se entiende {marca}.")
    origen = Path(texto[len(prefijo):].splitlines()[0].strip())
    if not (origen / "cliente").is_dir():
        raise ErrorEntorno(f"No encuentro la carpeta cliente de la instalación en uso ({origen}).")
    return origen


def crear(origen, destino, rama="experimental", puerto=8865, copiar=True, avisar=print):
    origen, destino = Path(origen).resolve(), Path(destino).resolve()
    if (origen / MARCA).exists():
        raise ErrorEntorno("Esta carpeta ya es un entorno de pruebas: ejecutalo desde la instalación en uso.")
    if not (origen / ".git").exists():
        raise ErrorEntorno(f"{origen} no es un repositorio de git.")
    if destino.exists():
        raise ErrorEntorno(f"{destino} ya existe. Elegí otro --destino o borrá esa carpeta de pruebas.")
    if destino == origen or origen in destino.parents:
        raise ErrorEntorno("El entorno de pruebas tiene que estar fuera de la carpeta sistema.")
    if puerto in (PUERTO_PRODUCCION, PUERTO_PRODUCCION + 1) or not 1024 <= puerto < 65535:
        raise ErrorEntorno(f"Elegí un puerto distinto de {PUERTO_PRODUCCION}/{PUERTO_PRODUCCION + 1} (los de producción).")
    _rama_valida(rama, origen)

    url = _git("remote", "get-url", "origin", cwd=origen, comprobar=False).stdout.strip()
    avisar(f"Clonando {origen} en {destino}...")
    _git("clone", "--quiet", "--no-checkout", str(origen), str(destino), cwd=origen.parent)
    if url:
        _git("remote", "set-url", "origin", url, cwd=destino)
        if _git("fetch", "--quiet", "origin", cwd=destino, comprobar=False).returncode != 0:
            avisar("Aviso: no se pudo consultar GitHub; se usan las ramas que ya conocía esta PC.")
    remota = _git("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{rama}", cwd=destino,
                  comprobar=False).returncode == 0
    if remota:
        _git("checkout", "--quiet", "-b", rama, "--track", f"origin/{rama}", cwd=destino)
    else:
        _git("checkout", "--quiet", "-b", rama, "origin/main", cwd=destino)
        avisar(f"Aviso: la rama {rama} no está en GitHub; se creó desde main. Publicala con: git push -u origin {rama}")

    (destino / MARCA).write_text(f"Entorno de pruebas creado desde {origen}\n", encoding="utf-8")
    with open(destino / ".git" / "info" / "exclude", "a", encoding="utf-8") as f:   # sirve en cualquier rama
        f.write(f"\n# entorno de pruebas (crear_entorno_pruebas.py)\n/{MARCA}\n/iniciar_pruebas.bat\n/iniciar_pruebas.sh\n"
                f"/cliente/{PERFIL_APP}\n")
    preparar_config(origen, destino)
    copiados = []
    if copiar:
        for nombre in COPIAR:
            if (origen / nombre).is_dir():
                shutil.copytree(origen / nombre, destino / nombre)
                copiados.append(nombre)
    python = _python_produccion(origen)
    escribir_lanzadores(destino, python, puerto)
    app = preparar_app(origen, destino)
    return {"destino": destino, "rama": rama, "puerto": puerto, "copiados": copiados, "python": python, "app": app}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Crea una copia aislada para probar ramas experimentales.")
    ap.add_argument("--rama", default="experimental", help="rama a probar (por defecto: experimental)")
    ap.add_argument("--destino", default=str(AQUI.parent / "sistema_pruebas"),
                    help="carpeta nueva para la copia (por defecto: ..\\sistema_pruebas)")
    ap.add_argument("--puerto", type=int, default=8865, help="puerto de la interfaz de pruebas (por defecto 8865)")
    ap.add_argument("--sin-copiar", action="store_true", help="no copiar conocimiento/ ni modelos/")
    ap.add_argument("--preparar-app", action="store_true",
                    help="en un entorno ya creado: solo prepara la app para compilarla y probarla (perfil de pruebas)")
    a = ap.parse_args(argv)
    if a.preparar_app:
        try:
            if (AQUI / MARCA).exists():
                destino, origen = AQUI, origen_del_entorno(AQUI)
            else:
                destino, origen = Path(a.destino).resolve(), AQUI
                origen_del_entorno(destino)
            copiado = preparar_app(origen, destino)
        except (ErrorEntorno, OSError) as ex:
            print(f"[ERROR] {ex}", file=sys.stderr)
            return 1
        print(f"App preparada en {destino / 'cliente'} (perfil de pruebas). Copiado de {origen / 'cliente'}: "
              f"{', '.join(copiado) or 'nada (faltan las bibliotecas de WebView2 en producción)'}.")
        print("Compilar: powershell -NoProfile -ExecutionPolicy Bypass -File cliente_codigo\\compilar.ps1")
        return 0
    try:
        r = crear(AQUI, a.destino, a.rama, a.puerto, copiar=not a.sin_copiar)
    except ErrorEntorno as ex:
        print(f"[ERROR] {ex}", file=sys.stderr)
        return 1
    lanzador = "iniciar_pruebas.bat" if os.name == "nt" else "./iniciar_pruebas.sh"
    print(f"\nListo. Entorno de pruebas en {r['destino']} (rama {r['rama']}).")
    print(f"Copiado: {', '.join(r['copiados']) or 'nada'} · Python: {r['python']}")
    print(f"Para abrirlo: {lanzador}  →  http://127.0.0.1:{r['puerto']}")
    print(f"App de prueba: {', '.join(r['app']) or 'sin bibliotecas de WebView2'} + cliente\\{PERFIL_APP} "
          "(compilala con cliente_codigo\\compilar.ps1)")
    print("Trabajá y commiteá dentro de esa carpeta; la instalación en uso no cambia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
