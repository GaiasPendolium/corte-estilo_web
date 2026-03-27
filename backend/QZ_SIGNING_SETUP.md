# QZ Tray Signing Setup (Django)

Este backend expone:
- `GET /api/qz/certificate/` -> retorna `certificate.pem`
- `POST /api/qz/sign/` -> firma `toSign` con `private-key.pem` (SHA256 + RSA)

## 1) Generar llaves y certificado

Recomendado: usar OpenSSL en tu maquina de despliegue/CI.

```bash
openssl req -x509 -newkey rsa:2048 -keyout private-key.pem -out certificate.pem -days 3650 -nodes -subj "/CN=corte-estilo-web.vercel.app/O=Corte y Estilo/C=CO"
```

Opcional (si deseas formato PKCS8 explicito para la key):

```bash
openssl pkcs8 -topk8 -inform PEM -outform PEM -in private-key.pem -out private-key-pkcs8.pem -nocrypt
```

## 2) Variables de entorno backend

Guarda el contenido PEM completo (incluye BEGIN/END) en variables:

- `QZ_CERT_PEM`
- `QZ_PRIVATE_KEY_PEM`
- `QZ_ALLOWED_ORIGINS=https://corte-estilo-web.vercel.app`

Si tienes varios frontends, separa por comas:

```text
QZ_ALLOWED_ORIGINS=https://corte-estilo-web.vercel.app,https://otro-frontend.vercel.app
```

## 3) Variables de entorno frontend

```text
VITE_QZ_SIGN_ENDPOINT=https://TU_BACKEND/api/qz
VITE_QZ_CERT_PEM=
```

Nota: deja `VITE_QZ_CERT_PEM` vacio si quieres que el frontend lo descargue desde `/certificate`.

## 4) Prueba rapida

1. Abrir QZ Tray en Windows.
2. En frontend, seleccionar impresora POS.
3. Ejecutar una impresion.
4. Verificar en DevTools:
   - `GET https://TU_BACKEND/api/qz/certificate/` -> 200 texto PEM
   - `POST https://TU_BACKEND/api/qz/sign/` -> 200 firma base64
5. En QZ Tray, el sitio debe aparecer como confiable y dejar de mostrar `Invalid Certificate / Untrusted website`.

## 5) Seguridad basica

- No publiques `QZ_PRIVATE_KEY_PEM` en frontend.
- Limita `QZ_ALLOWED_ORIGINS` a dominios reales.
- Usa HTTPS en frontend y backend.
