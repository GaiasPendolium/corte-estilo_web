# Integracion SAT TP-1580 y SAT 119X

Este proyecto web usa un puente local para comunicarse con impresora termica y cajon monedero.

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
