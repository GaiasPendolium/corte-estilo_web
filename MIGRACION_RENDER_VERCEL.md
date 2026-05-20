# Migracion temporal a Render + Vercel

Esta guia deja el backend en Render (Django + PostgreSQL) y el frontend en Vercel.

## 1. Backend en Render

1. En Render, crea un nuevo Blueprint y conecta este repositorio.
2. Render detectara automaticamente el archivo `render.yaml`.
3. Espera a que se creen:
   - Servicio web `peluqueria-backend`
   - Base de datos `peluqueria-postgres`
4. Cuando termine el primer deploy, ejecuta migraciones desde Shell de Render:

```bash
python manage.py migrate
python manage.py createsuperuser
```

5. Copia la URL publica del backend, por ejemplo:

```text
https://peluqueria-backend.onrender.com
```

Tu API queda en:

```text
https://peluqueria-backend.onrender.com/api
```

## 2. Frontend en Vercel

1. Importa el repositorio en Vercel.
2. Define en Environment Variables (Production/Preview):

```text
VITE_API_URL=https://peluqueria-backend.onrender.com/api
VITE_QZ_SIGN_ENDPOINT=https://peluqueria-backend.onrender.com/api/qz
```

3. Deploy.

## 3. Variables importantes en Render

Ademas de las del `render.yaml`, revisa:

```text
ALLOWED_HOSTS=peluqueria-backend.onrender.com
CORS_ALLOWED_ORIGINS=https://tu-frontend.vercel.app
CSRF_TRUSTED_ORIGINS=https://tu-frontend.vercel.app
DEBUG=False
```

Si tienes dominio propio, agrega tambien esos dominios separados por coma.

## 4. Verificacion rapida

1. Backend:

```text
GET https://peluqueria-backend.onrender.com/health/
```

Debe responder:

```json
{"status":"ok"}
```

2. Frontend: login normal en Vercel.
3. Si falla CORS, agrega el dominio exacto de Vercel a `CORS_ALLOWED_ORIGINS` y `CSRF_TRUSTED_ORIGINS`.

## 5. Nota sobre backup

Cuando Railway vuelva, puedes exportar y luego restaurar en Render usando:

```bash
pg_dump "URL_POSTGRES_RAILWAY" -Fc -f backup_railway.dump
pg_restore --no-owner --no-privileges -d "URL_POSTGRES_RENDER" backup_railway.dump
```
