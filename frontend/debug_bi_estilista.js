// Script de debugging para inspeccionar el desglose del BI de un estilista
// Copia esto en la consola del navegador (F12):

async function debugBIEstilista(estilistaId, fechaInicio, fechaFin) {
  const token = localStorage.getItem('access_token');
  if (!token) {
    console.error('❌ No hay token de autenticación. Inicia sesión primero.');
    return;
  }

  const url = `/api/reportes/bi/desglose/?estilista_id=${estilistaId}&fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}`;
  
  console.log(`🔍 Debugeando BI para estilista ${estilistaId}...`);
  console.log(`📅 Período: ${fechaInicio} a ${fechaFin}`);
  
  try {
    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      const error = await response.json();
      console.error('❌ Error:', error);
      return;
    }

    const data = await response.json();
    
    // Imprimir en tabla
    console.log('\n✅ DATOS OBTENIDOS');
    console.table({
      'Estilista': data.estilista.nombre,
      'Tipo cobro': data.estilista.tipo_cobro_espacio,
      'Valor cobro': data.estilista.valor_cobro_espacio,
      'Total servicios': data.servicios.total_precio_cobrado,
      'Total comisión': data.comisiones.total_comision,
      'Días trabajados': data.resumen.total_dias,
      'Neto pendiente': data.resumen.pago_neto_pendiente,
      'Neto cancelado': data.resumen.pago_neto_cancelado,
      'Neto período': data.resumen.pago_neto_periodo,
    });

    console.log('\n📊 DESGLOSE POR DÍA:');
    console.table(data.desglose_por_dia);

    console.log('\n💰 DETALLE DE VENTAS DE PRODUCTOS:');
    console.table(data.comisiones.detalle_ventas);

    console.log('\n📋 DATOS COMPLETOS (JSON):');
    console.log(JSON.stringify(data, null, 2));

  } catch (error) {
    console.error('❌ Error en la request:', error);
  }
}

// Uso:
// debugBIEstilista(1, '2026-03-22', '2026-03-22')  // Reemplaza 1 con el ID del estilista
// O en el navegador puedes hacer click derecho, Inspect, y en la consola pegar esto:
// debugBIEstilista(estilistaId, fechaInicio, fechaFin)
