# Integracion SAT TP-1580 y SAT 119X

Este proyecto web usa un puente local para comunicarse con impresora termica y cajon monedero.

## Configuracion facil (maquina SAT sin proyecto completo)

Si la maquina SAT no tiene el proyecto web, usa este modo portable:

1. Copia SOLO la carpeta `local_bridge` a la maquina SAT (por USB o red).
2. Dentro de esa carpeta, ejecuta `instalar_bridge_sat.bat` (una sola vez).
3. Luego ejecuta `iniciar_bridge_sat.bat` cada vez que abras caja/facturacion.
4. Opcional: usa `verificar_bridge_sat.bat` para comprobar estado.

Con esto no necesitas clonar ni instalar todo el proyecto en la maquina SAT.

## 1) Instalar bridge local (Windows)

1. Abrir terminal en `peluqueria_web/local_bridge`.
2. Instalar dependencias:

```bash
pip install -r requirements.txt
```

3. Configurar impresora SAT (opcional por variable de entorno):

```powershell
$env:SAT_PRINTER_NAME="SAT TP-1580"
$env:SAT_ENCODING="cp850"
```

4. Ejecutar bridge:

```bash
python sat_bridge.py
```

Bridge queda en: `http://127.0.0.1:8787`

## 2) Configurar frontend

En `peluqueria_web/frontend/.env` agregar:

```env
VITE_POS_BRIDGE_URL=http://127.0.0.1:8787
```

Reiniciar frontend despues del cambio.

## 3) Uso operativo

- Boton `Imprimir` en Historico de ventas envia factura al bridge.
- Boton `Abrir caja` envia pulso ESC/POS al cajon SAT 119X conectado a la impresora.

## 4) Notas tecnicas

- El navegador no puede enviar comandos RAW directo a USB/COM en todos los escenarios.
- Por eso se usa puente local para impresion ESC/POS y apertura de cajon.
- Si el cajon no abre, validar cable RJ11 del cajon hacia impresora y nombre de cola de impresion.
