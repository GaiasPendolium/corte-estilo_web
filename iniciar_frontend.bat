@echo off
setlocal
echo ==========================================
echo  Corte y Estilo - Frontend (Vite)
echo ==========================================

cd /d "%~dp0"

echo Iniciando servidor en http://localhost:3000 (o el siguiente puerto libre)
echo Mantener esta ventana abierta mientras se use el sistema.
echo.

cd frontend
npm run dev
