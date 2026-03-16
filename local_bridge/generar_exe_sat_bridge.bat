@echo off
setlocal
echo ==========================================
echo  Generador EXE SAT Bridge Manager
echo ==========================================

cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python Launcher ^(py^) no encontrado.
  pause
  exit /b 1
)

echo [1/5] Creando entorno virtual de build...
py -m venv .venv_build
if errorlevel 1 (
  echo [ERROR] No se pudo crear .venv_build
  pause
  exit /b 1
)

call .venv_build\Scripts\activate.bat
echo [2/5] Actualizando pip...
python -m pip install --upgrade pip

echo [3/5] Instalando dependencias del bridge...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Fallo instalando requirements
  pause
  exit /b 1
)

echo [4/5] Instalando pyinstaller...
python -m pip install pyinstaller==6.11.1
if errorlevel 1 (
  echo [ERROR] Fallo instalando pyinstaller
  pause
  exit /b 1
)

echo [5/5] Generando EXE...
pyinstaller --noconfirm --onefile --windowed --name SATBridgeManager sat_bridge_gui.py
if errorlevel 1 (
  echo [ERROR] No se pudo generar el EXE
  pause
  exit /b 1
)

echo.
echo EXE generado en:
echo %CD%\dist\SATBridgeManager.exe
echo.
echo Copia ese EXE a la maquina SAT y ejecutalo con doble clic.
pause
