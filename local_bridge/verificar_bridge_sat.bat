@echo off
setlocal
echo Verificando bridge en http://127.0.0.1:8787/status
powershell -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8787/status).Content } catch { Write-Host $_; exit 1 }"
pause
