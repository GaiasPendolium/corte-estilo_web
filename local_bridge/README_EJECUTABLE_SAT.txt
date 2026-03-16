SATBridgeManager.exe - Guia rapida

OBJETIVO
Usar SAT TP-1580 y SAT 119X en la web con doble clic, sin abrir terminal.

PASOS EN TU MAQUINA DE DESARROLLO
1) Abrir carpeta local_bridge.
2) Ejecutar: generar_exe_sat_bridge.bat
3) Tomar archivo generado en dist\SATBridgeManager.exe

PASOS EN LA MAQUINA SAT
1) Copiar SATBridgeManager.exe
2) Doble clic para abrir
3) Seleccionar impresora SAT TP-1580
4) Clic en Guardar config
5) Clic en Iniciar bridge
6) Verificar estado en http://127.0.0.1:8787/status

EN LA WEB
Configurar variable de frontend:
VITE_POS_BRIDGE_URL=http://127.0.0.1:8787

NOTA
Mantener la app SATBridgeManager abierta mientras se factura.
