@echo off
setlocal
echo ==========================================
echo  SAT Bridge - Iniciar servicio local
echo ==========================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] No existe entorno virtual.
  echo Ejecuta primero instalar_bridge_sat.bat
  pause
  exit /b 1
)

set "SAT_PRINTER_NAME=SAT TP-1580"
set "SAT_ENCODING=cp850"

echo Impresora configurada: %SAT_PRINTER_NAME%
echo URL Bridge: http://127.0.0.1:8787/status
echo.
echo Mantener esta ventana abierta mientras se use caja/facturacion.
echo.

.venv\Scripts\python.exe sat_bridge.py
