# 🚀 Sistema de Gestión para Peluquería - Corte y Estilo

Sistema web moderno y responsive para gestión de peluquería desarrollado con Django (Backend) y React (Frontend).

## 📋 Características

- ✅ **Autenticación JWT** - Sistema seguro de inicio de sesión
- 👥 **Gestión de Usuarios** - Control de acceso por roles (Administrador, Empleado, Visualizador)
- ✂️ **Gestión de Estilistas** - Registro y seguimiento de estilistas
- 💼 **Servicios** - Catálogo de servicios con precios y duración
- 📦 **Inventario de Productos** - Control de stock con alertas de reposición
- 💰 **Registro de Ventas** - Ventas de productos y servicios realizados
- 📊 **Reportes y Estadísticas** - Dashboard con métricas en tiempo real
- 📱 **Diseño Responsive** - Compatible con dispositivos móviles y tablets
- 🎨 **Interfaz Moderna** - UI elegante y profesional con TailwindCSS

## 🛠️ Tecnologías Utilizadas

### Backend
- Django 5.0
- Django REST Framework
- Simple JWT (Autenticación)
- SQLite (Desarrollo) / PostgreSQL (Producción recomendado)
- Python 3.10+

### Frontend
- React 18
- Vite (Build tool)
- TailwindCSS (Estilos)
- React Router (Navegación)
- Axios (HTTP Client)
- Zustand (State Management)
- React Icons
- React Toastify (Notificaciones)

## 📁 Estructura del Proyecto

```
peluqueria_web/
├── backend/                    # Aplicación Django
│   ├── peluqueria_backend/    # Configuración del proyecto
│   ├── api/                   # API REST
│   ├── manage.py
│   └── requirements.txt
│
└── frontend/                  # Aplicación React
    ├── src/
    │   ├── components/       # Componentes reutilizables
    │   ├── pages/            # Páginas principales
    │   ├── services/         # Servicios API
    │   ├── store/            # Estado global (Zustand)
    │   ├── App.jsx
    │   └── main.jsx
    ├── package.json
    └── vite.config.js
```

## 🚀 Instalación y Configuración

### Requisitos Previos

- Python 3.10 o superior
- Node.js 18 o superior
- npm o yarn

### 1️⃣ Configuración del Backend (Django)

#### Paso 1: Navegar a la carpeta del backend
```powershell
cd peluqueria_web/backend
```

#### Paso 2: Crear y activar entorno virtual
```powershell
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
.\venv\Scripts\Activate.ps1
```

#### Paso 3: Instalar dependencias
```powershell
pip install -r requirements.txt
```

#### Paso 4: Configurar variables de entorno
Copiar el archivo `.env.example` y renombrarlo a `.env`:
```powershell
Copy-Item .env.example .env
```

Editar `.env` y configurar las variables necesarias (puedes usar valores por defecto para desarrollo).

#### Paso 5: Ejecutar migraciones
```powershell
python manage.py makemigrations
python manage.py migrate
```

#### Paso 6: Crear superusuario
```powershell
python manage.py createsuperuser
```
Sigue las instrucciones en pantalla para crear tu primer usuario administrador.

#### Paso 7: Iniciar servidor de desarrollo
```powershell
python manage.py runserver
```

El backend estará disponible en: `http://localhost:8000`
Panel de administración: `http://localhost:8000/admin`

### 2️⃣ Configuración del Frontend (React)

Abrir una **nueva terminal** (dejar el backend corriendo).

#### Paso 1: Navegar a la carpeta del frontend
```powershell
cd peluqueria_web/frontend
```

#### Paso 2: Instalar dependencias
```powershell
npm install
```

#### Paso 3: Configurar variables de entorno
Copiar el archivo `.env.example` y renombrarlo a `.env`:
```powershell
Copy-Item .env.example .env
```

El archivo `.env` debe contener:
```
VITE_API_URL=http://localhost:8000/api
```

#### Paso 4: Iniciar servidor de desarrollo
```powershell
npm run dev
```

El frontend estará disponible en: `http://localhost:3000`

## 🔐 Acceso al Sistema

1. Abre tu navegador en `http://localhost:3000`
2. Inicia sesión con el usuario que creaste en el paso 6 del backend
3. Explora las diferentes secciones del sistema

## 📊 Módulos del Sistema

### Dashboard
- Vista general de estadísticas
- Ingresos del mes actual
- Alertas de productos con bajo stock
- Métricas de ventas y servicios

### Usuarios
- Crear, editar y eliminar usuarios
- Asignar roles (Administrador, Empleado, Visualizador)
- Cambiar contraseñas

### Estilistas
- Registro de estilistas
- Configurar comisiones por servicio
- Estadísticas de servicios realizados

### Servicios
- Catálogo de servicios
- Precio y duración de cada servicio
- Activar/desactivar servicios

### Productos (Inventario)
- Control de stock
- Alertas de stock mínimo
- Ajustes de inventario
- Registro de movimientos

### Ventas
- Registro de ventas de productos
- Actualización automática de inventario
- Historial de ventas

### Reportes
- Reportes de ventas por fecha
- Reportes de servicios realizados
- Estadísticas generales
- Exportación a CSV (opcional)

## 🎨 Personalización

### Cambiar colores del tema

Edita el archivo `frontend/tailwind.config.js`:
```javascript
theme: {
  extend: {
    colors: {
      primary: {
        // Personaliza tus colores aquí
      }
    }
  }
}
```

### Cambiar logo y nombre

Edita los siguientes archivos:
- `frontend/src/pages/Login.jsx` - Logo en página de login
- `frontend/src/components/Layout.jsx` - Logo en sidebar
- `frontend/index.html` - Título de la página

## 🔧 Comandos Útiles

### Backend
```powershell
# Crear migraciones
python manage.py makemigrations

# Aplicar migraciones
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Ejecutar tests
python manage.py test

# Recolectar archivos estáticos (producción)
python manage.py collectstatic
```

### Frontend
```powershell
# Instalar dependencias
npm install

# Desarrollo
npm run dev

# Build para producción
npm run build

# Preview de producción
npm run preview

# Linting
npm run lint
```

## 🚀 Despliegue a Producción

### Backend (Django)

1. Configurar base de datos PostgreSQL
2. Actualizar `settings.py` con configuraciones de producción
3. Configurar `DEBUG = False`
4. Configurar `ALLOWED_HOSTS`
5. Configurar servidor web (Nginx + Gunicorn recomendado)
6. Configurar HTTPS con Let's Encrypt

### Frontend (React)

1. Ejecutar `npm run build`
2. Desplegar carpeta `dist/` en servidor web o CDN
3. Configurar variables de entorno de producción
4. Configurar dominio y HTTPS

### Opciones de hosting recomendadas:
- **Backend**: Railway, Render, DigitalOcean, AWS
- **Frontend**: Vercel, Netlify, Cloudflare Pages
- **Base de datos**: PostgreSQL en Railway, Supabase, o AWS RDS

## 🐛 Solución de Problemas

### El backend no inicia
- Verifica que el entorno virtual esté activado
- Verifica que todas las dependencias estén instaladas
- Revisa los errores en la consola

### El frontend no se conecta al backend
- Verifica que el backend esté corriendo en `http://localhost:8000`
- Verifica la variable `VITE_API_URL` en `.env`
- Revisa la consola del navegador para errores

### Error de CORS
- Verifica `CORS_ALLOWED_ORIGINS` en `backend/peluqueria_backend/settings.py`
- Asegúrate de incluir la URL del frontend

### Error de autenticación
- Verifica que el token JWT no haya expirado
- Intenta cerrar sesión y volver a iniciar
- Limpia el localStorage del navegador

## 📝 Licencia

Este proyecto es de código privado para uso interno de la empresa.

## 👥 Soporte

Para soporte técnico o preguntas, contacta al equipo de desarrollo.

---

**Desarrollado con ❤️ para Corte y Estilo**
