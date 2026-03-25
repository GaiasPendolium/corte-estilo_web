from django.db import migrations


POSTGRES_STATEMENTS = [
    "DROP TABLE IF EXISTS estado_pago_estilista_dia CASCADE",
    """
CREATE TABLE estado_pago_estilista_dia (
    id BIGSERIAL PRIMARY KEY,
    fecha DATE NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    ganancias_totales NUMERIC(12,2) NOT NULL DEFAULT 0,
    descuento_puesto NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_pagable NUMERIC(12,2) NOT NULL DEFAULT 0,
    pago_efectivo NUMERIC(12,2) NOT NULL DEFAULT 0,
    pago_nequi NUMERIC(12,2) NOT NULL DEFAULT 0,
    pago_daviplata NUMERIC(12,2) NOT NULL DEFAULT 0,
    pago_otros NUMERIC(12,2) NOT NULL DEFAULT 0,
    abono_puesto NUMERIC(12,2) NOT NULL DEFAULT 0,
    saldo_puesto_pendiente NUMERIC(12,2) NOT NULL DEFAULT 0,
    neto_dia NUMERIC(12,2) NULL DEFAULT 0,
    pendiente_puesto NUMERIC(12,2) NULL DEFAULT 0,
    notas VARCHAR(255) NULL,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    estilista_id BIGINT NOT NULL,
    usuario_liquida_id BIGINT NULL,
    CONSTRAINT estado_pago_estilista_dia_estilista_id_fecha_uniq UNIQUE (estilista_id, fecha),
    CONSTRAINT estado_pago_estilista_dia_estilista_fk
        FOREIGN KEY (estilista_id) REFERENCES estilistas (id) ON DELETE CASCADE,
    CONSTRAINT estado_pago_estilista_dia_usuario_liquida_fk
        FOREIGN KEY (usuario_liquida_id) REFERENCES usuarios (id) ON DELETE SET NULL
);
""",
    "CREATE INDEX estado_pago_estilista_dia_fecha_idx ON estado_pago_estilista_dia (fecha)",
    "CREATE INDEX estado_pago_estilista_dia_estilista_idx ON estado_pago_estilista_dia (estilista_id)",
]


SQLITE_STATEMENTS = [
    "DROP TABLE IF EXISTS estado_pago_estilista_dia",
    """
CREATE TABLE estado_pago_estilista_dia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha DATE NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    ganancias_totales NUMERIC(12,2) NOT NULL DEFAULT 0,
    descuento_puesto NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_pagable NUMERIC(12,2) NOT NULL DEFAULT 0,
    pago_efectivo NUMERIC(12,2) NOT NULL DEFAULT 0,
    pago_nequi NUMERIC(12,2) NOT NULL DEFAULT 0,
    pago_daviplata NUMERIC(12,2) NOT NULL DEFAULT 0,
    pago_otros NUMERIC(12,2) NOT NULL DEFAULT 0,
    abono_puesto NUMERIC(12,2) NOT NULL DEFAULT 0,
    saldo_puesto_pendiente NUMERIC(12,2) NOT NULL DEFAULT 0,
    neto_dia NUMERIC(12,2) NULL DEFAULT 0,
    pendiente_puesto NUMERIC(12,2) NULL DEFAULT 0,
    notas VARCHAR(255) NULL,
    actualizado_en DATETIME NOT NULL,
    estilista_id INTEGER NOT NULL,
    usuario_liquida_id INTEGER NULL,
    FOREIGN KEY (estilista_id) REFERENCES estilistas (id) ON DELETE CASCADE,
    FOREIGN KEY (usuario_liquida_id) REFERENCES usuarios (id) ON DELETE SET NULL
);
""",
    "CREATE UNIQUE INDEX estado_pago_estilista_dia_estilista_id_fecha_uniq ON estado_pago_estilista_dia (estilista_id, fecha)",
    "CREATE INDEX estado_pago_estilista_dia_fecha_idx ON estado_pago_estilista_dia (fecha)",
    "CREATE INDEX estado_pago_estilista_dia_estilista_idx ON estado_pago_estilista_dia (estilista_id)",
]


def recreate_estado_pago_estilista_dia(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == 'postgresql':
        for statement in POSTGRES_STATEMENTS:
            schema_editor.execute(statement)
    elif vendor == 'sqlite':
        for statement in SQLITE_STATEMENTS:
            schema_editor.execute(statement)
    else:
        raise RuntimeError(f'Base de datos no soportada para esta migracion: {vendor}')


def noop_reverse(apps, schema_editor):
    # La reconstruccion es intencionalmente destructiva y no reversible.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0022_estadopagoestilistadia_descuento_puesto_and_more'),
    ]

    operations = [
        migrations.RunPython(recreate_estado_pago_estilista_dia, reverse_code=noop_reverse),
    ]
