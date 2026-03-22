@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
  echo [INFO] Creando entorno virtual...
  py -m venv .venv
)

call .venv\Scripts\activate
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt

if not exist drawer_config.json (
  if exist drawer_config.example.json copy /Y drawer_config.example.json drawer_config.json >nul
)

echo [INFO] Iniciando servicio de cajon serial en http://127.0.0.1:5000
echo [INFO] Endpoint: GET /abrir-cajon
python serial_drawer_flask.py

endlocal
