## 🚀 Despliegue Rápido: 5 Pasos

**Requisitos:**
- Cuenta GitHub
- Cuenta Railway (https://railway.app) 
- Cuenta Vercel (https://vercel.app)

---

### **PASO 1: Subir código a GitHub**

```bash
cd c:\Users\slbqu\OneDrive\Documents\Proyecto\peluqueria_web
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/peluqueria-salon.git
git push -u origin main
```

---

### **PASO 2: Desplegar Backend en Railway (10 minutos)**

1. Ve a https://railway.app
2. Log in con GitHub
3. Click "New Project" → "Deploy from GitHub"
4. Selecciona tu repo `peluqueria-salon`
5. Railway detecta que es Django automáticamente ✓

**Cuando esté desplegado:**
- Tu backend estará en: `https://peluqueria-salon.up.railway.app/api/`
- Railway crea automáticamente las variables: `PORT`, `DATABASE_URL` (si agregas PostgreSQL)

**Variables a configurar en Railway:**
```
VARIABLES A AGREGAR:
- DEBUG=False
- SECRET_KEY=choose-a-random-secure-key
- ALLOWED_HOSTS=peluqueria-salon.up.railway.app
- CORS_ALLOWED_ORIGINS=https://peluqueria-salon.vercel.app
```

**Opcional: Agregar PostgreSQL**
- En Railway: "Add Service" → "PostgreSQL"
- Railway llena automáticamente `DATABASE_URL` ✓

---

### **PASO 3: Desplegar Frontend en Vercel (5 minutos)**

1. Ve a https://vercel.com
2. Log in con GitHub  
3. Click "Add New..." → "Project"
4. Selecciona `peluqueria-salon`
5. Configura variable de entorno:
   - `VITE_API_URL=https://peluqueria-salon.up.railway.app/api`
6. Click "Deploy" ✓

**Tu app estará en:** `https://peluqueria-salon.vercel.app`

---

### **PASO 4: Prueba**

```
1. Abre https://peluqueria-salon.vercel.app
2. Login con: usuario=admin, contraseña=admin123
3. Prueba descargar un reporte (CSV/PDF)
4. Si sale error 401, revisa variables en Railway
```

---

### **PASO 5: Futuras actualizaciones**

Simplemente haz `git push`:
```bash
git add .
git commit -m "Cambios"
git push origin main
```

Railway y Vercel desplegarán automáticamente en 2-5 minutos. ✓

---

## 📚 Documentación Completa

Ve al archivo **DEPLOY_GUIDE.md** para troubleshooting y opciones avanzadas.

---

**¡Tu app estará en internet en 15 minutos! 🎉**
