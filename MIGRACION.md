# Migración de Datos desde la Aplicación Local

Esta guía te ayudará a migrar los datos de tu aplicación Flet local a la nueva aplicación web Django + React.

## 📋 Pasos para Migrar

### 1. Exportar datos de SQLite antiguo

La aplicación antigua usa SQLite (archivo `peluqueria.db`). Primero necesitas ubicar este archivo en tu carpeta del proyecto original.

### 2. Crear script de migración

Crea un archivo `migrate_data.py` en la carpeta `backend/`:

```python
import sqlite3
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'peluqueria_backend.settings')
django.setup()

from api.models import Usuario, Estilista, Servicio, Producto, ServicioRealizado, VentaProducto, MovimientoInventario
from django.utils import timezone
from datetime import datetime

# Ruta a tu base de datos antigua
OLD_DB_PATH = '../../peluqueria_app/peluqueria.db'

def migrate_usuarios():
    """Migrar usuarios"""
    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_cursor = old_conn.cursor()
    
    old_cursor.execute('SELECT * FROM usuarios')
    usuarios = old_cursor.fetchall()
    
    for u in usuarios:
        usuario, created = Usuario.objects.get_or_create(
            username=u[1],
            defaults={
                'nombre_completo': u[3],
                'rol': u[4],
                'activo': bool(u[5]),
                'fecha_creacion': u[6] if u[6] else timezone.now()
            }
        )
        if created:
            usuario.set_password(u[2])  # La contraseña está hasheada con bcrypt
            usuario.save()
            print(f'✓ Usuario migrado: {usuario.username}')
    
    old_conn.close()

def migrate_estilistas():
    """Migrar estilistas"""
    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_cursor = old_conn.cursor()
    
    old_cursor.execute('SELECT * FROM estilistas')
    estilistas = old_cursor.fetchall()
    
    for e in estilistas:
        Estilista.objects.get_or_create(
            id=e[0],
            defaults={
                'nombre': e[1],
                'telefono': e[2],
                'email': e[3],
                'comision_porcentaje': e[4] or 0,
                'activo': bool(e[5]),
                'fecha_ingreso': e[6]
            }
        )
        print(f'✓ Estilista migrado: {e[1]}')
    
    old_conn.close()

def migrate_servicios():
    """Migrar servicios"""
    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_cursor = old_conn.cursor()
    
    old_cursor.execute('SELECT * FROM servicios')
    servicios = old_cursor.fetchall()
    
    for s in servicios:
        Servicio.objects.get_or_create(
            id=s[0],
            defaults={
                'nombre': s[1],
                'descripcion': s[2],
                'precio': s[3],
                'duracion_minutos': s[4],
                'activo': bool(s[5])
            }
        )
        print(f'✓ Servicio migrado: {s[1]}')
    
    old_conn.close()

def migrate_productos():
    """Migrar productos"""
    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_cursor = old_conn.cursor()
    
    old_cursor.execute('SELECT * FROM productos')
    productos = old_cursor.fetchall()
    
    for p in productos:
        Producto.objects.get_or_create(
            id=p[0],
            defaults={
                'codigo_barras': p[1],
                'nombre': p[2],
                'descripcion': p[3],
                'precio_compra': p[4],
                'precio_venta': p[5],
                'stock': p[6] or 0,
                'stock_minimo': p[7] or 5,
                'activo': bool(p[8])
            }
        )
        print(f'✓ Producto migrado: {p[2]}')
    
    old_conn.close()

def migrate_servicios_realizados():
    """Migrar servicios realizados"""
    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_cursor = old_conn.cursor()
    
    old_cursor.execute('SELECT * FROM servicios_realizados')
    servicios = old_cursor.fetchall()
    
    for s in servicios:
        try:
            ServicioRealizado.objects.get_or_create(
                id=s[0],
                defaults={
                    'estilista_id': s[1],
                    'servicio_id': s[2],
                    'fecha_hora': s[3],
                    'precio_cobrado': s[4],
                    'notas': s[5]
                }
            )
            print(f'✓ Servicio realizado migrado: {s[0]}')
        except Exception as e:
            print(f'✗ Error migrando servicio realizado {s[0]}: {e}')
    
    old_conn.close()

def migrate_ventas():
    """Migrar ventas de productos"""
    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_cursor = old_conn.cursor()
    
    old_cursor.execute('SELECT * FROM ventas_productos')
    ventas = old_cursor.fetchall()
    
    for v in ventas:
        try:
            VentaProducto.objects.get_or_create(
                id=v[0],
                defaults={
                    'producto_id': v[1],
                    'cantidad': v[2],
                    'precio_unitario': v[3],
                    'total': v[4],
                    'fecha_hora': v[5],
                    'usuario_id': v[6] if v[6] else None
                }
            )
            print(f'✓ Venta migrada: {v[0]}')
        except Exception as e:
            print(f'✗ Error migrando venta {v[0]}: {e}')
    
    old_conn.close()

def migrate_movimientos_inventario():
    """Migrar movimientos de inventario"""
    old_conn = sqlite3.connect(OLD_DB_PATH)
    old_cursor = old_conn.cursor()
    
    old_cursor.execute('SELECT * FROM movimientos_inventario')
    movimientos = old_cursor.fetchall()
    
    for m in movimientos:
        try:
            MovimientoInventario.objects.get_or_create(
                id=m[0],
                defaults={
                    'producto_id': m[1],
                    'tipo_movimiento': m[2],
                    'cantidad': m[3],
                    'fecha_hora': m[4],
                    'descripcion': m[5],
                    'usuario_id': m[6] if m[6] else None
                }
            )
            print(f'✓ Movimiento migrado: {m[0]}')
        except Exception as e:
            print(f'✗ Error migrando movimiento {m[0]}: {e}')
    
    old_conn.close()

if __name__ == '__main__':
    print('🚀 Iniciando migración de datos...\n')
    
    print('📝 Migrando usuarios...')
    migrate_usuarios()
    
    print('\n✂️ Migrando estilistas...')
    migrate_estilistas()
    
    print('\n💼 Migrando servicios...')
    migrate_servicios()
    
    print('\n📦 Migrando productos...')
    migrate_productos()
    
    print('\n💇 Migrando servicios realizados...')
    migrate_servicios_realizados()
    
    print('\n💰 Migrando ventas...')
    migrate_ventas()
    
    print('\n📊 Migrando movimientos de inventario...')
    migrate_movimientos_inventario()
    
    print('\n✅ ¡Migración completada!')
```

### 3. Ejecutar el script de migración

```powershell
cd backend
python migrate_data.py
```

### 4. Verificar datos migrados

Puedes verificar que los datos se migraron correctamente:

1. Accede al panel de administración en `http://localhost:8000/admin`
2. Revisa cada modelo (Usuarios, Estilistas, Servicios, etc.)
3. O ejecuta en el shell de Django:

```powershell
python manage.py shell
```

```python
from api.models import Usuario, Estilista, Servicio, Producto

print(f'Usuarios: {Usuario.objects.count()}')
print(f'Estilistas: {Estilista.objects.count()}')
print(f'Servicios: {Servicio.objects.count()}')
print(f'Productos: {Producto.objects.count()}')
```

## ⚠️ Notas Importantes

1. **Contraseñas**: Las contraseñas en la antigua aplicación usan bcrypt. Necesitarás:
   - Mantener los hashes bcrypt en la nueva base de datos, O
   - Resetear las contraseñas de todos los usuarios después de la migración

2. **IDs**: Los IDs se mantendrán igual que en la base de datos antigua para preservar las relaciones.

3. **Backup**: Haz un backup de tu base de datos antigua antes de migrar:
   ```powershell
   Copy-Item peluqueria_app/peluqueria.db peluqueria_app/peluqueria.db.backup
   ```

4. **Fechas**: Las fechas se migrarán tal como están. Verifica que el timezone sea correcto.

## 🔄 Migración de Archivos (si aplica)

Si tienes archivos adjuntos (imágenes, documentos), cópialos manualmente:

```powershell
# Copiar archivos de assets
Copy-Item -Recurse peluqueria_app/assets/* peluqueria_web/backend/media/
```

## ✅ Checklist Post-Migración

- [ ] Verificar que todos los usuarios se migraron
- [ ] Verificar estilistas y sus comisiones
- [ ] Verificar catálogo de servicios
- [ ] Verificar inventario de productos y stock
- [ ] Verificar historial de servicios realizados
- [ ] Verificar historial de ventas
- [ ] Probar inicio de sesión con usuarios migrados
- [ ] Verificar permisos por rol
- [ ] Revisar reportes y estadísticas

## 🆘 Solución de Problemas

### La base de datos antigua no se encuentra
- Verifica la ruta en `OLD_DB_PATH`
- Asegúrate de que el archivo `peluqueria.db` existe

### Errores de integridad al migrar
- Verifica que las relaciones (foreign keys) sean correctas
- Asegúrate de migrar en el orden correcto (primero usuarios, luego referencias)

### Las contraseñas no funcionan
- Si usaste bcrypt en la app antigua, necesitarás configurar Django para usar bcrypt también
- O resetear las contraseñas de todos los usuarios

---

🎉 ¡Listo! Tus datos ahora están en la nueva aplicación web.
