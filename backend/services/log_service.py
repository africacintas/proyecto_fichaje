"""
log_service.py — Servicio de auditoría y logging
==================================================
Registra en base de datos las acciones relevantes del sistema
(logins, fichajes, acciones de administrador) y configura
el logging de Python para escribir en archivo y consola.
"""

import logging
import logging.handlers
import os
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from models import LogAcceso


# ── Configuración del logger de Python ───────────────────────────────────────

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR   = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)


def configurar_logging():
    """
    Configura el sistema de logging de Python con dos handlers:
      1. Consola (stdout): útil para ver logs con 'docker-compose logs'.
      2. Archivo rotatorio: guarda hasta 5 archivos de 5 MB cada uno.
    """
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler de consola.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Handler de archivo rotatorio.
    file_handler = logging.handlers.RotatingFileHandler(
        filename    = f"{LOG_DIR}/fichaje.log",
        maxBytes    = 5 * 1024 * 1024,  # 5 MB
        backupCount = 5,
        encoding    = "utf-8",
    )
    file_handler.setFormatter(formatter)

    # Aplicar configuración al logger raíz de la aplicación.
    root_logger = logging.getLogger("fichaje")
    root_logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


# ── Registro de auditoría en base de datos ────────────────────────────────────

def registrar_log(
    db: Session,
    accion: str,
    usuario_id: Optional[int] = None,
    detalle: Optional[str] = None,
    ip: Optional[str] = None,
):
    """
    Inserta un registro de auditoría en la tabla logs_acceso.
    Se usa para rastrear acciones importantes: logins, fichajes,
    altas de usuarios, decisiones sobre preavisos, etc.
    """
    entrada = LogAcceso(
        usuario_id = usuario_id,
        accion     = accion,
        detalle    = detalle,
        ip         = ip,
        timestamp  = datetime.now(timezone.utc),
    )
    db.add(entrada)
    db.commit()
