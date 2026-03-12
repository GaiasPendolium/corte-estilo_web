# Inicio Rápido - Sistema de Gestión Peluquería

## 🚀 Pasos rápidos para iniciar el proyecto

### 1. Backend (Terminal 1)

```powershell
# Navegar a la carpeta backend
cd peluqueria_web/backend

# Crear y activar entorno virtual
python -m venv venv
.\venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt

# Configurar base de datos
python manage.py migrate

# Crear superusuario (seguir instrucciones)
python manage.py createsuperuser

# Iniciar servidor
python manage.py runserver
```

### 2. Frontend (Terminal 2)

```powershell
# Navegar a la carpeta frontend
cd peluqueria_web/frontend

# Instalar dependencias
npm install

# Crear archivo .env
Copy-Item .env.example .env

# Iniciar servidor de desarrollo
npm run dev
```

### 3. Acceder al sistema

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000/api
- **Admin Django**: http://localhost:8000/admin

### 4. Credenciales

Usa las credenciales del superusuario que creaste en el paso 1.

---

## 📝 Comandos útiles después de la instalación

### Poblar con datos de ejemplo (opcional)

Crea un archivo `backend/populate_data.py`:

```python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'peluqueria_backend.settings')
django.setup()

from api.models import Usuario, Estilista, Servicio, Producto

# Crear usuarios de ejemplo
Usuario.objects.create_user(
    username='empleado1',
    password='password123',
    nombre_completo='Juan Pérez',
    rol='empleado'
)

# Crear estilistas de ejemplo
Estilista.objects.create(
    nombre='María García',
    telefono='555-1234',
    email='maria@example.com',
    comision_porcentaje=15.00
)

# Crear servicios de ejemplo
Servicio.objects.create(
    nombre='Corte de Cabello',
    descripcion='Corte básico para caballero',
    precio=150.00,
    duracion_minutos=30
)

Servicio.objects.create(
    nombre='Tinte',
    descripcion='Aplicación de tinte',
    precio=500.00,
    duracion_minutos=90
)

# Crear productos de ejemplo
Producto.objects.create(
    nombre='Shampoo',
    codigo_barras='1234567890',
    precio_compra=80.00,
    precio_venta=150.00,
    stock=20,
    stock_minimo=5
)

print('✅ Datos de ejemplo creados exitosamente')
```

Ejecutar:
```powershell
python populate_data.py
```

---

## 🔧 Reiniciar base de datos (si algo sale mal)

```powershell
cd backend

# Eliminar base de datos y migraciones
Remove-Item db.sqlite3
Remove-Item api\migrations\0*.py

# Recrear todo
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
```

---

¡Listo para empezar! 🎉
