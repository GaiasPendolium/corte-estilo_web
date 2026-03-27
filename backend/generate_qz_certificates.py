#!/usr/bin/env python3
"""
Script para generar certificados y claves para QZ Tray.
Uso: python generate_qz_certificates.py
"""

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from datetime import datetime, timedelta
import os

DOMAIN = "corte-estilo-web.vercel.app"
DAYS_VALID = 3650  # 10 años
OUTPUT_CERT = "certificate.pem"
OUTPUT_KEY = "private-key.pem"


def generate_self_signed_cert(domain, days=3650):
    """Genera certificado autofirmado RSA 2048."""
    
    # Generar clave privada
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    
    # Construir certificado
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CO"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Colombia"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Corte y Estilo"),
        x509.NameAttribute(NameOID.COMMON_NAME, domain),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=days)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(domain),
            x509.DNSName("*.vercel.app"),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256(), default_backend())
    
    return cert, private_key


def save_pem_files(cert, private_key, cert_path, key_path):
    """Guarda certificado y clave en archivos PEM."""
    
    # Guardar certificado
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    with open(cert_path, "wb") as f:
        f.write(cert_pem)
    print(f"✓ Certificado guardado: {cert_path}")
    
    # Guardar clave privada
    key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(key_path, "wb") as f:
        f.write(key_pem)
    print(f"✓ Clave privada guardada: {key_path}")
    
    return cert_pem, key_pem


def print_env_vars(cert_pem, key_pem):
    """Imprime las variables de entorno listas para copiar a Railway."""
    
    cert_str = cert_pem.decode("utf-8")
    key_str = key_pem.decode("utf-8")
    
    print("\n" + "="*80)
    print("VARIABLES PARA COPIAR A RAILWAY")
    print("="*80)
    print("\nQZ_CERT_PEM (copiar todo incluyendo BEGIN/END):")
    print(cert_str)
    print("\nQZ_PRIVATE_KEY_PEM (copiar todo incluyendo BEGIN/END):")
    print(key_str)
    print("\nQZ_ALLOWED_ORIGINS:")
    print("https://corte-estilo-web.vercel.app")
    print("\n" + "="*80)


if __name__ == "__main__":
    print(f"Generando certificados para {DOMAIN} ({DAYS_VALID} días válido)...\n")
    
    cert, private_key = generate_self_signed_cert(DOMAIN, DAYS_VALID)
    cert_pem, key_pem = save_pem_files(cert, private_key, OUTPUT_CERT, OUTPUT_KEY)
    
    print("\n✓ Certificados creados exitosamente.\n")
    
    print_env_vars(cert_pem, key_pem)
    
    print("\nPasos siguientes:")
    print("1. Copiar QZ_CERT_PEM a Railway → Variables → QZ_CERT_PEM")
    print("2. Copiar QZ_PRIVATE_KEY_PEM a Railway → Variables → QZ_PRIVATE_KEY_PEM")
    print("3. Copiar QZ_ALLOWED_ORIGINS a Railway → Variables → QZ_ALLOWED_ORIGINS")
    print("4. Redeploy backend en Railway")
    print("5. Frontend ya tiene la variable VITE_QZ_SIGN_ENDPOINT configurada")
    print("6. Redeploy frontend en Vercel")
    print("\nLuego prueba nuevamente con QZ Tray.")
