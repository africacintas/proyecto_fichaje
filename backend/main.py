"""
main.py — Punto de entrada del backend (FastAPI)
=================================================
Inicializa la aplicación, configura el logging, registra
todos los routers y crea las tablas en la base de datos.
"""

import time
import logging
from sqlalchemy.exc import OperationalError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from models import engine, Base, SessionLocal, Usuario
from services import hash_password, configurar_logging
from routes import auth_router, usuarios_router, fichajes_router, alertas_router, documentos_router

import os

# Configurar el sistema de logging antes de cualquier otra operación.
configurar_logging()
logger = logging.getLogger("fichaje.main")


# ─────────────────────────────────────────────────────────────────────────────
# APLICACIÓN FASTAPI
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "API — Sistema de Control de Presencia",
    description = "Control de jornada laboral con geolocalización GPS. TFG ASIR.",
    version     = "2.0.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

# Middleware CORS: permite peticiones desde el frontend en desarrollo.
app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],   # En producción, especificar el dominio real.
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)

# Registro de routers por módulo funcional.
app.include_router(auth_router)
app.include_router(usuarios_router)
app.include_router(fichajes_router)
app.include_router(alertas_router)
app.include_router(documentos_router)


@app.get("/", tags=["Sistema"])
def health_check():
    """Endpoint de comprobación de salud del servicio."""
    return {"status": "ok", "version": "2.0.0"}


# ─────────────────────────────────────────────────────────────────────────────
# INICIALIZACIÓN DE LA BASE DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

def inicializar_base_de_datos():
    """
    Crea las tablas si no existen y genera el administrador por defecto.
    Reintenta hasta 5 veces para tolerar el tiempo de arranque de PostgreSQL
    en Docker Compose (aunque el healthcheck ya lo gestiona parcialmente).
    """
    for intento in range(5):
        try:
            Base.metadata.create_all(bind=engine)
            db = SessionLocal()

            ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL", "admin@empresa.com")
            ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin1234")
            ADMIN_NOMBRE   = os.getenv("ADMIN_NOMBRE", "Administrador")

            if not db.query(Usuario).filter(Usuario.email == ADMIN_EMAIL).first():
                db.add(Usuario(
                    nombre        = ADMIN_NOMBRE,
                    email         = ADMIN_EMAIL,
                    password_hash = hash_password(ADMIN_PASSWORD),
                    rol           = "admin",
                ))
                db.commit()
                logger.info(f"Administrador inicial creado: {ADMIN_EMAIL}")

            db.close()
            logger.info("Base de datos inicializada correctamente.")
            return

        except OperationalError:
            logger.warning(f"BD no disponible, reintentando... ({intento + 1}/5)")
            time.sleep(5)

    raise RuntimeError("No se pudo conectar a la base de datos tras 5 intentos.")


inicializar_base_de_datos()

# Cargar datos de prueba si SEED_DATA=true (por defecto activo en desarrollo).
# Poner SEED_DATA=false en el .env de producción para no sobrescribir datos reales.
if os.getenv("SEED_DATA", "true").lower() == "true":
    try:
        from seed import seed
        seed()
    except Exception as e:
        logger.warning(f"Seed de datos omitido o ya ejecutado: {e}")
