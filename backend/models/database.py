"""
database.py — Configuración de la conexión a PostgreSQL
=========================================================
Crea el motor SQLAlchemy, la sesión y la clase Base
que heredan todos los modelos ORM.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://fichaje_user:dev@db:5432/gestion_fichajes")

engine       = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


def get_db():
    """
    Generador de sesión de base de datos para usar como dependencia en FastAPI.
    Garantiza el cierre de la sesión al finalizar cada petición.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
