@echo off
setlocal
echo ==========================================
echo  Instalador SAT Bridge (TP-1580 / 119X)
echo ==========================================

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% neq 0 (
  echo [ERROR] Python Launcher (py) no encontrado.
  echo Instala Python 3.11+ y marca "Add Python to PATH".
  pause
  exit /b 1
)

echo [1/3] Creando entorno virtual...
py -m venv .venv
if %errorlevel% neq 0 (
  echo [ERROR] No se pudo crear el entorno virtual.
  pause
  exit /b 1
)

echo [2/3] Instalando dependencias...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo [ERROR] Fallo instalando dependencias.
  pause
  exit /b 1
)

echo [3/3] Instalacion completada.
echo Usa iniciar_bridge_sat.bat para ejecutar el bridge.
pause
