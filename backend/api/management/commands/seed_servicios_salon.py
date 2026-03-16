from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Servicio, ServicioRealizado, VentaProducto


SERVICIOS_SALON = [
    ('Corte dama', 'Corte y diseno para dama', '45000.00', 45),
    ('Corte caballero', 'Corte clasico o moderno para caballero', '25000.00', 30),
    ('Corte infantil', 'Corte para ninos y ninas', '22000.00', 30),
    ('Lavado y secado', 'Lavado profesional y secado basico', '18000.00', 25),
    ('Brushing corto', 'Cepillado para cabello corto', '28000.00', 35),
    ('Brushing largo', 'Cepillado para cabello largo', '38000.00', 45),
    ('Planchado', 'Planchado y acabado liso', '30000.00', 35),
    ('Ondas', 'Ondas y peinado con herramienta termica', '38000.00', 45),
    ('Peinado social', 'Peinado para evento social', '55000.00', 60),
    ('Recogido', 'Recogido para ocasion especial', '70000.00', 75),
    ('Trenzas basicas', 'Trenzado sencillo', '25000.00', 35),
    ('Trenzas elaboradas', 'Disenos de trenzas avanzadas', '60000.00', 90),
    ('Aplicacion de tinte', 'Coloracion global', '85000.00', 120),
    ('Retoque de raiz', 'Retoque en crecimiento de raiz', '65000.00', 90),
    ('Bano de color', 'Reavivado de color', '70000.00', 90),
    ('Mechas', 'Aplicacion de mechas', '130000.00', 180),
    ('Balayage', 'Tecnica de aclarado balayage', '220000.00', 240),
    ('Decoloracion', 'Proceso de decoloracion', '160000.00', 210),
    ('Matizacion', 'Neutralizacion de tonos no deseados', '70000.00', 80),
    ('Alisado progresivo', 'Alisado y control de frizz', '220000.00', 210),
    ('Keratina', 'Tratamiento de keratina', '180000.00', 180),
    ('Botox capilar', 'Tratamiento de nutricion profunda', '160000.00', 150),
    ('Hidratacion capilar', 'Tratamiento hidratante', '65000.00', 60),
    ('Reconstruccion capilar', 'Tratamiento reparador', '90000.00', 75),
    ('Cauterizacion', 'Sellado de fibra capilar', '100000.00', 90),
    ('Permanente', 'Moldeado permanente', '120000.00', 140),
    ('Relajante', 'Proceso de relajacion capilar', '120000.00', 120),
    ('Perfilado de cejas', 'Diseno y perfilado de cejas', '15000.00', 20),
    ('Depilacion cejas', 'Depilacion con cera o hilo', '12000.00', 15),
    ('Diseno de cejas', 'Diseno de acuerdo al rostro', '25000.00', 25),
    ('Laminado de cejas', 'Fijacion y peinado de cejas', '60000.00', 45),
    ('Depilacion bozo', 'Depilacion de bozo', '10000.00', 10),
    ('Maquillaje social', 'Maquillaje para evento', '90000.00', 75),
    ('Maquillaje profesional', 'Maquillaje de larga duracion', '140000.00', 100),
    ('Manicure tradicional', 'Limpieza y esmalte tradicional', '28000.00', 45),
    ('Manicure semipermanente', 'Esmaltado semipermanente', '45000.00', 60),
    ('Pedicure tradicional', 'Pedicure basico', '35000.00', 50),
    ('Pedicure spa', 'Pedicure con exfoliacion e hidratacion', '55000.00', 70),
    ('Unas acrilicas', 'Aplicacion de unas acrilicas', '110000.00', 120),
    ('Retoque unas', 'Mantenimiento de unas', '70000.00', 80),
    ('Extensiones de cabello', 'Instalacion de extensiones', '250000.00', 180),
    ('Retiro de extensiones', 'Retiro seguro de extensiones', '70000.00', 60),
    ('Tratamiento anticaida', 'Tratamiento para fortalecimiento', '95000.00', 70),
    ('Masaje capilar', 'Masaje relajante del cuero cabelludo', '25000.00', 20),
    ('Asesoria de imagen', 'Asesoria de estilo y look', '50000.00', 40),
    ('Servicio adicional shampoo', 'Adicional de shampoo durante servicio', '10000.00', 5),
    ('Servicio adicional ampolla', 'Adicional de ampolla o tratamiento corto', '18000.00', 10),
]


class Command(BaseCommand):
    help = 'Carga un catalogo amplio de servicios de salon y opcionalmente limpia ventas/servicios finalizados.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-sales-finalized',
            action='store_true',
            help='Borra todas las ventas y servicios finalizados antes de cargar servicios.',
        )

    def handle(self, *args, **options):
        clear_sales_finalized = options.get('clear_sales_finalized', False)

        with transaction.atomic():
            ventas_borradas = 0
            finalizados_borrados = 0

            if clear_sales_finalized:
                ventas_borradas, _ = VentaProducto.objects.all().delete()
                finalizados_borrados, _ = ServicioRealizado.objects.filter(estado='finalizado').delete()

            creados = 0
            actualizados = 0
            for nombre, descripcion, precio, duracion in SERVICIOS_SALON:
                _, creado = Servicio.objects.update_or_create(
                    nombre=nombre,
                    defaults={
                        'descripcion': descripcion,
                        'precio': Decimal(precio),
                        'duracion_minutos': duracion,
                        'es_adicional': 'adicional' in nombre.lower(),
                        'activo': True,
                    },
                )
                if creado:
                    creados += 1
                else:
                    actualizados += 1

        self.stdout.write(self.style.SUCCESS('Proceso completado'))
        self.stdout.write(
            f'ventas_borradas={ventas_borradas} servicios_finalizados_borrados={finalizados_borrados} '
            f'servicios_creados={creados} servicios_actualizados={actualizados} total_servicios={Servicio.objects.count()}'
        )
