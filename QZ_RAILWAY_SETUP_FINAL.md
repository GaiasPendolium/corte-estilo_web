**GUÍA PASO A PASO: Configurar QZ Tray en Railway + Vercel (Solución completa)**

## El Problema

En QZ Tray sales "An anonymous request wants to access connected printers - Untrusted website"  
porque no hay certificado válido ni firma para tu dominio Vercel.

## La Solución: 5 pasos simples

---

### PASO 1: Copiar certificados a Railway variables ✅

**Ya fueron generados en:** `peluqueria_web/backend/generate_qz_certificates.py`

1. Abre **Railway dashboard**: https://railway.app
2. Selecciona proyecto `corte&estilo` (backend)
3. Ve a **Variables** (o Environment)
4. Copia y pega exactamente esto (incluye BEGIN/END):

```
QZ_CERT_PEM
```
Valor:
```
-----BEGIN CERTIFICATE-----
MIIDhDCCAmygAwIBAgIUGZRUQ9oC5iNv1qFp+DN1BBdQutgwDQYJKoZIhvcNAQEL
BQAwXzELMAkGA1UEBhMCQ08xETAPBgNVBAgMCENvbG9tYmlhMRcwFQYDVQQKDA5D
b3J0ZSB5IEVzdGlsbzEkMCIGA1UEAwwbY29ydGUtZXN0aWxvLXdlYi52ZXJjZWwu
YXBwMB4XDTI2MDMyNzE3MjM1OVoXDTM2MDMyNDE3MjM1OVowXzELMAkGA1UEBhMC
Q08xETAPBgNVBAgMCENvbG9tYmlhMRcwFQYDVQQKDA5Db3J0ZSB5IEVzdGlsbzEk
MCIGA1UEAwwbY29ydGUtZXN0aWxvLXdlYi52ZXJjZWwuYXBwMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1vgH3lkIdQ+KpyB76nF1fs9gekGOIzcH0kmU
c8dOA4jm21T1MxNkxF7/bCMmTa2pugw3IhoNcSWZiGpvmsVNH2dLvs3gc4KxILgv
BJrzhU/rZYJNgv3eEczxVw/mc6QTHba5f9dXTd6hij9XYSDsguiLmx6CI6IIlZaz
PdbHd8fK2j+/49Eb4j0S5xEW/Kf6v4ij/Ol0HhmrwHE4BIhl3267PTqP6gVc0dpg
Fnqc7uHoHPBBFbf6zfGg5AY2zXiLNBTsO19mguiBc881/Xq8IMTmXhuW43yRngEw
qnO1U66tb97SRGS21tXJqoS2CZb31X3kD/DGHRDzX5vI0Cis9wIDAQABozgwNjA0
BgNVHREELTArghtjb3J0ZS1lc3RpbG8td2ViLnZlcmNlbC5hcHCCDCoudmVyY2Vs
LmFwcDANBgkqhkiG9w0BAQsFAAOCAQEAWRk9LMU1j+MX9mE1X0IsTcboJ95R5Xxk
7QlWuJyjj/ktRF8lXt77WZZlobE7jzuqbHJoaSqwUylsISxB6NNFZjWSgTr6g95q
h1xfMpz6JQMa6g1EWtlXG2axA64xB8UkMZt3dOIk4Y2eRanoxpQ8DXv+bLOkH1yQ
UvESBUD2iwSoNOcFRfmysxFFxxSJ9+BPcxvrLJzRVbhhZVRiYwoaFxjR3C1br40r
L4KfgRA2J/TuoFUJvlnheK0j3Pi37CVm7MB96UME/JLDocNZ39b5PWm+NJ0Unsxd
32hH5kj2OWre4pgJXyW3FxFTyBql7RaXzq3Dku1j10NPNhNXjgAKxA==
-----END CERTIFICATE-----
```

---

5. Añade nueva variable: `QZ_PRIVATE_KEY_PEM`

```
-----BEGIN RSA PRIVATE KEY-----
MIIEogIBAAKCAQEA1vgH3lkIdQ+KpyB76nF1fs9gekGOIzcH0kmUc8dOA4jm21T1
MxNkxF7/bCMmTa2pugw3IhoNcSWZiGpvmsVNH2dLvs3gc4KxILgvBJrzhU/rZYJN
gv3eEczxVw/mc6QTHba5f9dXTd6hij9XYSDsguiLmx6CI6IIlZazPdbHd8fK2j+/
49Eb4j0S5xEW/Kf6v4ij/Ol0HhmrwHE4BIhl3267PTqP6gVc0dpgFnqc7uHoHPBB
Fbf6zfGg5AY2zXiLNBTsO19mguiBc881/Xq8IMTmXhuW43yRngEwqnO1U66tb97S
RGS21tXJqoS2CZb31X3kD/DGHRDzX5vI0Cis9wIDAQABAoIBAGcHRS4p2cXRBxEG
np1Ed52pYoH1vVvfWh5NKZs74IYNLSfd1g7+soLzTNPVHNyJ6RjEFgCAIAUkkisx
Z//zo/zzEviFz5dNAfu+irpYUXKJVTa3dtLbPX2mjdy+QCMYdhj9pHZDDRLDKwUJ
SqXAk9pB/fcAbjsJw7d+HLX8pGkhNZCA+wpAGiHkDACKjpeiop3YHFM3eYx3lH5N
o8zsooDj+gB/pgAT1+V6cBUourh7gpF3X45XjOqq9ov0lnIu/QtH5U7SCXk46Yrm
cj4E8FaTio7ZgPL5grBds9fun/rst24nLT9OV8Ab7edzMW2dhpZIxfv5BEgxnVbK
i3gVBkECgYEA7mBv7RUrCxMeYhCidQoKZFb2qCI7dFWKeMdwNFQcPSkKbmaHFEOC
l6UbT95xFzRjFtwMpS9JLu0AbSLDwxwf3Aec0Xs/q1ZZ+Q+DFTNe07lFVwsmkDwT
B5W+FGObu8FSlE3Qxjr1W2vCEAnab/y83n/pgSSkdnfQSyfz4rtdpycCgYEA5tyS
hVZGtFHhoTuz7urUiNvbqS7wVgvfFIpfAKLn4oKJLlYkPv+UCF8DtWEXddeGVvV3
i1t+iE+oDT7cv+Q5mv3PMYhl0jJKmikxE4AxVxKW+XhRRbuvtzwUEL0qW8lBGgGU
SW/jIZi4nwvlv0VPKvTsMfqUcF38yRN0C2uv7bECgYB6lILZ8sm4nzM/kHhKIUio
woOCgF/8ecSESWKsthfzZ3hivzx1MiYknxXFY4jaOuk9pxillQRYKi3O8VKjsYG8
nvmIS425KOWJiu2IaGs6CwraMPS6tPnAK8OcLoC18zro4n8agNUNFwOrRbXbYqco
77P+4f3kocYt77SdgmYtfwKBgGJKoTuR+zKE9jrOj5J2exz19rU2ne8UyNsW+tHr
iiz/hOasmGwWJvHVel+8Qd/TbogRpN85iksBFzzkedpdkkUyMQgW2bs/3FF8nj9+
QgOfj5YRqxC0k2DBfI2P7Lv9mPE4oOkPcTX5rwlQaHYiTU2tz+6LkK2y5pC57pt6
MwJRAoGADgzIb8+yJhN8mXgfrZkyKMtZccuKZ8bsgn23BbCdUomQhD85HPucLIjV
0UulCZRiapimKa8REr6TnjMyZAn9eLvZn7KGuDjhWNmVLFIXas+etRSpY4GSURcT
1rpm9oqwP2agSFyDDybrQGtPUH4paAM3OPQa+oTiOLqw8jFRUJg=
-----END RSA PRIVATE KEY-----
```

6. Añade nueva variable: `QZ_ALLOWED_ORIGINS`

Valor:
```
https://corte-estilo-web.vercel.app
```

---

### PASO 2: Redeploy backend en Railway ✅

Después de guardar las variables:

1. Ve a **Deployments** en Railway
2. Haz clic en el último deployment
3. Click **Redeploy**
4. Espera a que diga "✓ Deployment successful"

---

### PASO 3: Verificar que frontend tiene variable QZ ✅

**Ya está en:** `frontend/.env.local`

```
VITE_QZ_SIGN_ENDPOINT="https://corteandestilo-production.up.railway.app/api/qz"
```

Si está faltando, agrégala manualmente.

---

### PASO 4: Redeploy frontend en Vercel ✅

1. Push a GitHub (o Vercel ya detectará cambios):
   ```bash
   git add frontend/.env.local
   git commit -m "Add QZ signing endpoint"
   git push
   ```

2. Ve a https://vercel.com → proyecto **corte-estilo-web**
3. Espera a que despliegue automáticamente
4. O haz clic **Redeploy** manualmente

---

### PASO 5: Probar QZ Tray ✅

1. Abre la app en **https://corte-estilo-web.vercel.app**
2. Ve a **Impresión POS** (o cualquier pantalla que use QZ)
3. Intenta imprimir un ticket  
4. QZ Tray debe mostrame:
   - ✅ SIN "Invalid Certificate / Untrusted website"
   - ✅ Botón **Allow** disponible (sin rojo/bloqueado)
   - ✅ Checkbox "Remember this decision" debe funcionar

---

## ¿Qué está pasando detrás?

1. Frontend hace GET `/api/qz/certificate` desde navegador
2. Backend devuelve el `.pem` firmado
3. Frontend hace POST `/api/qz/sign` con datos a firmar
4. Backend usa la clave privada para firmar con SHA256
5. QZ Tray verifica firma y marca dominio como válido
6. No vuelve a pedir permisos en futuras impresiones

---

## Si todavía sale error

**Verifica:**

```bash
# 1. ¿Backend tiene variables?
curl https://corteandestilo-production.up.railway.app/api/qz/certificate/

# Debe devolver algo como:
# -----BEGIN CERTIFICATE-----
# ABCD1234...
# -----END CERTIFICATE-----

# 2. ¿Frontend ve el endpoint correcto?
# Abre DevTools → Network → filtra por "qz"
# Debe ver:
# GET .../api/qz/certificate → 200
# POST .../api/qz/sign → 200
```

---

## Resumen URLs configuradas

| Componente | URL |
|-----------|-----|
| Frontend | https://corte-estilo-web.vercel.app |
| Backend | https://corteandestilo-production.up.railway.app |
| Endpoint Certificado | `/api/qz/certificate/` |
| Endpoint Firma | `/api/qz/sign/` |
| Algoritmo | SHA256 + RSA 2048 |

---

**Listo. Después de estos pasos, QZ Tray debe confiar automáticamente en tu dominio. 🎉**
