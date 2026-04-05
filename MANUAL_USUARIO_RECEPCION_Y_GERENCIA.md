# Manual de Usuario

![Logo Corte y Estilo](frontend/public/corte_estilo_logo.png)

## Corte y Estilo Web

Versión del manual orientada a operación diaria, caja, ventas, inventario y reportes.

## Objetivo del sistema

La plataforma Corte y Estilo Web permite administrar la operación de la peluquería desde una sola interfaz:

- Registro de servicios diarios.
- Venta de productos.
- Control de inventario.
- Seguimiento de facturas e historial de ventas.
- Liquidación de empleados.
- Cierre de caja por medio de pago.
- Seguimiento de deuda del puesto y cartera de consumo de empleados.

## Roles contemplados en este manual

- Recepción.
- Gerencia.

Nota:
El rol Administrador tiene acceso adicional a usuarios, configuración de empleados e impresión POS, pero este manual se centra en Recepción y Gerencia porque son los perfiles operativos más usados.

## Acceso al sistema

## Inicio de sesión

1. Abra la URL del sistema en el navegador.
2. Ingrese usuario y contraseña.
3. Presione Iniciar sesión.
4. El sistema redirige al Dashboard.

## Cierre de sesión

1. En el menú lateral, ubique la sección del usuario al final.
2. Presione Cerrar Sesión.

## Menú principal

El menú lateral puede mostrar más o menos opciones según el rol del usuario.

Opciones comunes:

- Dashboard.
- Operación diaria.
- Inventario y Servicio.
- Histórico de ventas.
- Reportes.

Opciones adicionales para Gerencia:

- Usuarios.
- Empleados.
- Impresión POS.

## Diferencias entre Recepción y Gerencia

| Módulo | Recepción | Gerencia |
|---|---|---|
| Dashboard | Sí | Sí |
| Operación diaria | Sí | Sí |
| Inventario y Servicio | Consulta y apoyo operativo | Consulta y administración |
| Histórico de ventas | Consulta | Consulta, edición y control |
| Reportes | Parcial | Completo |
| Usuarios | No | Sí |
| Empleados | No | Sí |
| Impresión POS | No | Sí |

## Qué puede hacer Recepción

- Registrar servicios.
- Finalizar servicios.
- Registrar cobros y medios de pago.
- Consultar productos y servicios.
- Consultar histórico de ventas.
- Revisar cierre de caja.
- Revisar productos por agotarse.

## Qué puede hacer Gerencia

- Todo lo que hace Recepción.
- Revisar y operar la liquidación de empleados.
- Revisar cartera de consumo de empleados.
- Analizar cierre de caja completo.
- Gestionar productos, servicios y empleados.
- Exportar información de reportes.

## Flujo general recomendado por día

## Flujo para Recepción

1. Ingresar al sistema.
2. Revisar Dashboard para ver alertas o stock crítico.
3. Registrar los servicios del día en Operación diaria.
4. Finalizar cada servicio con su medio de pago.
5. Registrar ventas de productos cuando corresponda.
6. Consultar Histórico de ventas para validar facturas.
7. Revisar Reportes > Cierre de caja al finalizar la jornada.

## Flujo para Gerencia

1. Revisar Dashboard y Reportes.
2. Validar que los servicios del día estén finalizados.
3. Revisar cierre de caja por medio de pago.
4. Registrar liquidación de empleados por día.
5. Registrar abonos o pagos del puesto si corresponde.
6. Verificar deuda acumulada del puesto y cartera de consumos.
7. Ajustar catálogo, inventario o empleados si es necesario.

## Módulo: Dashboard

## Propósito

Resume la operación del negocio en indicadores rápidos.

## Qué muestra

- Venta neta.
- Ganancia del negocio.
- Stock crítico.
- Participación de servicios.
- Ticket promedio.
- Gráficos de comportamiento diario.
- Productos destacados.
- Empleados con mejor desempeño.

## Uso recomendado

- Recepción: usarlo como panel inicial para detectar alertas.
- Gerencia: usarlo para seguimiento general antes de entrar a Reportes.

## Módulo: Operación diaria

## Propósito

Registrar el trabajo del día, desde el inicio del servicio hasta su cobro final.

## Flujo básico

1. Seleccionar estilista.
2. Seleccionar cliente.
3. Seleccionar servicio.
4. Guardar el registro.
5. Cuando el servicio termine, abrirlo de nuevo para finalizarlo.
6. Ingresar precio cobrado si cambió.
7. Elegir medio de pago.
8. Registrar adicionales si existen.
9. Finalizar.

## Qué significa cada estado

- En proceso: el servicio ya fue creado pero no se ha cerrado.
- Finalizado: el servicio ya fue cobrado y entra a reportes.

## Reglas importantes

- Un servicio solo suma en reportes cuando está finalizado.
- El medio de pago debe quedar correctamente registrado al finalizar.
- Si se venden productos o adicionales dentro del servicio, deben quedar asignados correctamente para que entren a inventario y a reportes.

## Buenas prácticas

- Finalizar el servicio apenas se cobre.
- Verificar que el cliente y el estilista sean correctos antes de guardar.
- Revisar el valor final cuando haya descuentos o cobros especiales.

## Módulo: Inventario y Servicio

## Propósito

Controlar el catálogo de productos y servicios, así como el stock disponible.

## Uso para Recepción

- Consultar existencia y precio de productos.
- Buscar rápidamente productos o servicios.
- Validar disponibilidad antes de vender.

## Uso para Gerencia

- Crear productos.
- Editar precios.
- Actualizar stock.
- Configurar comisión del estilista por producto.
- Crear o editar servicios.

## Recomendaciones

- Mantener actualizado el stock mínimo.
- Verificar productos con alerta de agotarse.
- Revisar comisiones configuradas en productos porque impactan la liquidación del empleado.

## Módulo: Histórico de ventas

## Propósito

Consultar, auditar y rastrear facturas ya emitidas.

## Qué se puede hacer

- Buscar ventas por fecha.
- Filtrar por medio de pago.
- Consultar detalle de facturas.
- Revisar movimientos por cliente o empleado.

## Funciones de Gerencia

- Editar factura.
- Cancelar factura.
- Corregir transacciones si hubo error operativo.

## Recomendaciones

- Antes de cancelar una factura, validar si ya afectó inventario o reporte.
- Usar este módulo para aclarar diferencias entre caja y operación.

## Módulo: Reportes

## Propósito

Consolidar la operación financiera y operativa del negocio.

En Reportes hay cuatro focos principales:

1. Cierre de caja.
2. Liquidación de empleado.
3. Cartera de empleado.
4. Productos por agotarse.

## Uso correcto de los filtros

Todos los reportes dependen del rango de fechas seleccionado.

Recomendaciones:

- Para liquidar empleados, usar un solo día.
- Para cierre de caja, se puede usar un día o un rango.
- Si hay un descuadre, validar primero que los servicios estén finalizados.

## Submódulo: Cierre de caja

## Qué muestra

- Ingresos Totales.
- Liquidación Empleado.
- Ganancia Total.
- Ingreso por Servicios.
- Ingreso por Productos.
- Ingreso por Espacios.
- Cuadre por medio de pago.

## Cómo leer cada tarjeta

### Ingresos Totales

Representa el total de ingresos registrados en el período.

Incluye:

- Cobros de servicios.
- Ventas de productos.
- Abonos al puesto registrados como ingresos del establecimiento.

### Liquidación Empleado

Representa lo que efectivamente se ha pagado al empleado en ese período.

No significa lo que falta por pagar. Significa lo ya pagado.

### Ganancia Total

Se calcula como:

Ganancia Total = Ingresos Totales - Liquidación Empleado

### Ingreso por Servicios

Muestra el valor correspondiente a servicios dentro del cierre del período.

### Ingreso por Productos

Muestra el valor de ventas de productos en el período.

### Ingreso por Espacios

Muestra los abonos o pagos realizados por concepto de puesto o espacio.

## Cuadre por medio de pago

Es una tabla clave para validar caja.

Cada fila muestra:

- Medio.
- Ingresos.
- Liquidación.
- Ganancia.

### Cómo interpretarlo

- Ingresos: dinero que entra por ese medio.
- Liquidación: dinero pagado al empleado por ese medio.
- Ganancia: diferencia entre ingresos y salidas.

## Revisión recomendada del cierre

1. Confirmar que el rango de fechas sea correcto.
2. Verificar si todos los servicios del rango están finalizados.
3. Revisar ventas de productos.
4. Revisar si hubo abonos al puesto.
5. Comparar las tarjetas con la tabla Cuadre por medio de pago.

## Submódulo: Liquidación Empleado

## Objetivo

Determinar:

- Cuánto ganó el empleado.
- Cuánto debe del puesto ese día.
- Cuánto se le pagó realmente.
- Cuánto queda acumulado de deuda por puesto.

## Regla operativa aplicada

La liquidación del empleado debe considerar:

- Ganancias por servicios.
- Comisiones por ventas de productos.

Además:

- El empleado puede liquidarse el 100% de lo que ganó.
- El valor del puesto no reduce automáticamente lo que se le paga.
- El puesto se maneja como deuda aparte.
- El empleado puede abonar o pagar total o parcialmente esa deuda.
- El abono al puesto se suma como ingreso del establecimiento.

## Qué significa cada columna

### Valor total empleado

Es la suma de lo ganado por servicios del período.

### Comisiones

Es la comisión por venta de productos y otros conceptos que apliquen.

### Puesto

Muestra tres datos importantes:

- Debe hoy: lo que le corresponde pagar por el puesto ese día.
- Deuda acumulada: lo que viene debiendo en total por puesto.
- Pagado al empleado: lo que ya se le entregó al empleado en el período.

### Valor a liquidar

Es lo pendiente por pagar al empleado según lo ganado y lo ya abonado al trabajador.

### Pagos por medio

Permiten registrar cuánto se le entrega al empleado por:

- Efectivo.
- Nequi.
- Daviplata.
- Otros.

### Abono puesto

Permite registrar cuánto abona el empleado para cubrir deuda del puesto.

### Medio abono puesto

Indica por qué medio pagó el empleado ese abono. Esto impacta el cierre por medio de pago.

## Casos operativos importantes

### Caso 1: empleado gana y se le paga completo

- Se registra el pago total al empleado.
- Si no debe puesto, queda cancelado.
- Si debe puesto y no lo paga, puede quedar debiendo.

### Caso 2: empleado gana, se le paga completo y además abona al puesto

- Se registra el pago al empleado por los medios usados.
- Se registra el abono al puesto.
- El abono entra como ingreso del establecimiento.
- La deuda acumulada del puesto disminuye.

### Caso 3: empleado gana, se le paga completo, pero no alcanza para cubrir deuda del puesto

- Igual puede quedar liquidado al 100% como empleado.
- La deuda del puesto queda pendiente.

### Caso 4: empleado solo abona al puesto

- Ese abono debe registrarse en Abono puesto.
- Debe llevar su medio de pago correcto.

## Restricción recomendada de operación

No se debe registrar un abono al puesto mayor que la deuda total real del espacio.

Si se detecta un exceso, debe validarse antes de guardar.

## Pasos para liquidar correctamente un día

1. Seleccionar un solo día.
2. Revisar cuánto ganó el empleado entre servicios y comisiones.
3. Revisar cuánto debe hoy por puesto.
4. Revisar la deuda acumulada.
5. Ingresar cuánto se le paga al empleado por cada medio.
6. Ingresar cuánto abona al puesto.
7. Elegir el medio del abono al puesto.
8. Presionar Liquidar.
9. Verificar el mensaje final mostrado por el sistema.

## Submódulo: Cartera Empleado

## Objetivo

Controlar consumos de empleados registrados como deuda.

## Qué permite

- Consultar deudas pendientes.
- Registrar abonos.
- Editar abonos ya registrados.
- Ver historial de pagos.

## Cuándo usarlo

Cuando el empleado consume productos y no los paga inmediatamente.

## Diferencia entre cartera y puesto

- Cartera: deuda por consumo de productos del empleado.
- Puesto: deuda por alquiler o cobro del espacio de trabajo.

Son conceptos diferentes y deben registrarse por separado.

## Submódulo: Productos por agotarse

## Objetivo

Alertar sobre productos con stock bajo o crítico.

## Uso recomendado

- Recepción: consultar antes de vender o prometer disponibilidad.
- Gerencia: reponer stock y ajustar compras.

## Módulo: Empleados

Disponible para Gerencia.

## Qué se configura aquí

- Datos básicos del empleado.
- Tipo de cobro del espacio.
- Valor del cobro.
- Comisión de ventas de productos.

## Importancia

La configuración de este módulo afecta directamente:

- La liquidación diaria.
- La deuda de puesto.
- El cierre de caja.

## Módulo: Usuarios

Disponible para Gerencia y Administración según permisos del sistema.

## Qué permite

- Crear usuarios.
- Cambiar roles.
- Desactivar usuarios.
- Cambiar contraseñas.

## Módulo: Impresión POS

Disponible para Gerencia y Administración según permisos.

## Uso

- Configurar impresora térmica.
- Validar impresión POS.
- Probar integración con QZ Tray.

## Pantalla cliente

Es una ventana adicional pensada para mostrar al cliente el resumen de la transacción.

Puede usarse en un monitor secundario.

## Preguntas frecuentes

## ¿Por qué un servicio no aparece en reportes?

Porque probablemente sigue en proceso y no fue finalizado.

## ¿Por qué Liquidación Empleado aparece en cero?

Porque esa tarjeta refleja lo pagado realmente al empleado, no lo pendiente por liquidar.

## ¿Por qué Ingreso por Espacios puede cambiar el cierre?

Porque los abonos al puesto cuentan como ingreso del establecimiento y afectan el cuadro por medio de pago.

## ¿Qué revisar si hay diferencias en caja?

1. Rango de fechas.
2. Servicios finalizados.
3. Medios de pago correctos.
4. Ventas de productos.
5. Abonos al puesto.
6. Liquidaciones ya registradas.

## Buenas prácticas operativas

- Registrar cada servicio con su medio de pago correcto.
- Evitar dejar servicios sin finalizar.
- Liquidar empleados usando un solo día.
- Registrar el abono del puesto con su medio real.
- Revisar deuda acumulada del puesto antes de cerrar la jornada.
- Validar stock antes de vender productos.

## Checklist de cierre diario para Recepción

- Todos los servicios del día quedaron finalizados.
- Todas las ventas quedaron facturadas.
- Los medios de pago están correctos.
- Se revisó el cierre de caja.
- Se reportaron diferencias a gerencia si existen.

## Checklist de cierre diario para Gerencia

- Se revisó el cierre por medio de pago.
- Se revisó liquidación de empleados del día.
- Se revisó deuda del puesto y abonos.
- Se revisó cartera de consumo si aplica.
- Se revisaron productos críticos.

## Capturas y apoyos visuales

En el repositorio actual solo está disponible el logo institucional como imagen embebida en este manual.

Si deseas un manual con pantallazos reales del sistema, la recomendación es agregar al menos estas capturas:

1. Pantalla de inicio de sesión.
2. Dashboard principal.
3. Operación diaria con servicio en proceso.
4. Finalización de servicio con medio de pago.
5. Histórico de ventas.
6. Reportes > Cierre de caja.
7. Reportes > Liquidación de empleado.
8. Reportes > Cartera de empleado.
9. Inventario y alertas de productos.

## Archivo del manual

Este documento fue generado para servir como base operativa y puede seguir ampliándose con pantallazos, instructivos internos y procedimientos del negocio.