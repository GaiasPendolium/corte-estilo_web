@echo off
setlocal
echo ==========================================
echo  Corte y Estilo - Backend (Django)
echo ==========================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] No existe el entorno virtual en .venv
  echo Crea el entorno virtual antes de continuar.
  pause
  exit /b 1
)

echo Iniciando servidor en http://127.0.0.1:8000
echo Mantener esta ventana abierta mientras se use el sistema.
echo.

cd backend
"..\.venv\Scripts\python.exe" manage.py runserver
