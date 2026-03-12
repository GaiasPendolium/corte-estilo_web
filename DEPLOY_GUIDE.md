# 📦 Guía de Despliegue - Peluquería Salon App

Este documento te guía paso a paso para subir tu aplicación a la web usando **Railway** (backend) y **Vercel** (frontend).

---

## 🚀 Opción Recomendada: Railway + Vercel

### **PASO 1: Prepara tu repositorio Git**

Si aún no tienes Git configurado:

```bash
cd c:\Users\slbqu\OneDrive\Documents\Proyecto\peluqueria_web
git init
git add .
git commit -m "Initial commit - Peluqueria Salon App"
```

Sube a **GitHub** (o Gitlab/Gitea):
1. Ve a https://github.com/new
2. Crea un repo llamado `peluqueria-salon`
3. Sigue las instrucciones para pushear tu código:

```bash
git remote add origin https://github.com/TU_USUARIO/peluqueria-salon.git
git branch -M main
git push -u origin main
```

---

## 🚂 PASO 2: Desplegar Backend en Railway

### 2.1 Crear cuenta y proyecto en Railway

1. Ve a https://railway.app
2. Regístrate con GitHub
3. Autoriza Railway para acceder a tu GitHub

### 2.2 Crear nuevo proyecto

1. Click en "New Project" → "Deploy from GitHub repo"
2. Selecciona el repo `peluqueria-salon`
3. Railway detectará automáticamente que es Django

### 2.3 Configurar variables de entorno

En Railway Dashboard → Project → Variables:

```
SECRET_KEY=django-insecure-tu-clave-super-secreta-aqui
DEBUG=False
ALLOWED_HOSTS=tu-proyecto.up.railway.app,tudominio.com
CORS_ALLOWED_ORIGINS=https://tu-frontend.vercel.app,https://tudominio.com
DATABASE_URL=postgresql://user:pass@host:5432/dbname
```

**Railway generará automáticamente `DATABASE_URL` si agregas Plugin PostgreSQL:**
- En la pestaña "Plugins" → Agregar PostgreSQL
- El `DATABASE_URL` se llena automáticamente

### 2.4 Configurar dominio personalizado (opcional)

1. En Settings → Domains
2. Agrega tu dominio (ej: api.tudominio.com)
3. Configura los DNS records de tu dominio

### 2.5 Deploy automático

Railway hace deploy automático cada vez que haces `git push`. Espera 2-3 minutos.

Tu backend estará en: `https://tu-proyecto.up.railway.app/api/`

---

## 🎨 PASO 3: Desplegar Frontend en Vercel

### 3.1 Crear cuenta en Vercel

1. Ve a https://vercel.com
2. Sign up con GitHub
3. Autoriza Vercel

### 3.2 Importar proyecto

1. Click "Add New..." → "Project"
2. Selecciona tu repo `peluqueria-salon`
3. Vercel detectará que es React/Vite automáticamente

### 3.3 Configurar variables de entorno

En el formulario de importación o en Settings → Environment Variables:

```
VITE_API_URL=https://tu-proyecto.up.railway.app/api
```

### 3.4 Build settings

Vercel debería detectar automáticamente:
- **Framework Preset:** Other
- **Build Command:** `npm run build`
- **Output Directory:** `dist`

Si no, configúralo manualmente en Settings.

### 3.5 Deploy

Click "Deploy" y espera 3-5 minutos.

Tu frontend estará en: `https://tu-proyecto.vercel.app`

---

## 📝 PASO 4: Crear archivo `.env` local (para desarrollo)

En la carpeta backend:

```bash
cd backend
cp .env.example .env
```

Edita `.env` con valores locales:

```
DEBUG=True
SECRET_KEY=local-secret-key
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
DATABASE_URL=sqlite:///db.sqlite3
```

En la carpeta frontend:

```bash
cd frontend
cp .env.example .env.local
```

Edita `.env.local`:

```
VITE_API_URL=http://localhost:8000/api
```

---

## 🧪 PASO 5: Pruebas previas (opcional pero recomendado)

### Testa el backend localmente:

```bash
cd backend
python manage.py runserver
# Debe estar en http://localhost:8000/api/login/
```

### Testa el frontend localmente:

```bash
cd frontend
npm run dev
# Debe estar en http://localhost:5173
```

---

## ✅ PASO 6: Verifica la conexión

Una vez desplegados, prueba:

1. **Login en frontend:**
   - Ve a https://tu-proyecto.vercel.app
   - Prueba login: usuario `admin`, contraseña `admin123`

2. **Exporta reportes:**
   - En Reportes → Descargar CSV/PDF
   - Debe descargarse sin errores

3. **Revisa la consola:**
   - En navegador (F12), ve a Console
   - No debe haber errores 401/CORS

---

## 🐛 Troubleshooting

### Error 401 (Unauthorized)

**Causa:** Token JWT expirado o `CORS_ALLOWED_ORIGINS` mal configurado

**Solución:**
```
En Railway → Variables:
CORS_ALLOWED_ORIGINS=https://tu-frontend.vercel.app,https://www.tu-frontend.vercel.app
```

### Error 502 (Bad Gateway)

**Causa:** El servidor Django no inició correctamente

**Solución:**
- En Railway, ve a Logs y revisa qué error hay
- Verifica que `Procfile` sea correcto
- Verifica `requirements.txt` esté completo

### API no responde

**Causa:** `ALLOWED_HOSTS` no incluye el dominio de Railway

**Solución:**
```
ALLOWED_HOSTS=tu-proyecto.up.railway.app,api.tudominio.com,localhost
```

---

## 📊 Monitoreo

### Railway Dashboard:
- Logs en tiempo real
- Uso de RAM/CPU
- Status de la app
- Metrics

### Vercel Dashboard:
- Builds y deploys
- Performance Analytics
- Error Tracking

---

## 🔐 Seguridad Importante

Antes de ir a producción:

✅ Cambia `SECRET_KEY` a algo único y largo  
✅ Configura `DEBUG=False` en Railway  
✅ Usa PostgreSQL en lugar de SQLite  
✅ Activa HTTPS (Vercel y Railway lo hacen por defecto)  
✅ Configura CORS solo con tus dominios reales  
✅ Usa variables de entorno para credenciales  

---

## 💾 Hacer cambios después del deploy

Simplemente haz un `git push`:

```bash
git add .
git commit -m "Descripción del cambio"
git push origin main
```

Railway y Vercel desplegarán automáticamente en 2-5 minutos.

---

**¡Listo! Tu app estará en internet en 15-20 minutos.** 🎉

Cualquier duda, revisa los logs en los dashboards de Railway y Vercel.
