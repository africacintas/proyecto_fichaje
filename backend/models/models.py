"""
models.py — Modelos ORM (SQLAlchemy)
=====================================
Define las tablas de la base de datos con sus restricciones,
índices y relaciones. Cada clase representa una tabla.
"""

from datetime import datetime, date, timezone
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey,
    Date, Boolean, Index, CheckConstraint, func
)
from sqlalchemy.orm import relationship
from .database import Base


class Usuario(Base):
    """
    Empleado o administrador del sistema.
    La contraseña nunca se almacena en texto plano, solo su hash bcrypt.
    """
    __tablename__ = "usuarios"

    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String(100), nullable=False)
    email           = Column(String(150), unique=True, index=True, nullable=False)
    password_hash   = Column(String(255), nullable=False)
    rol             = Column(String(10), nullable=False, default="user")
    activo          = Column(Boolean, nullable=False, default=True)
    creado_en       = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Campos para protección contra fuerza bruta.
    intentos_login  = Column(Integer, default=0, nullable=False)
    bloqueado_hasta = Column(DateTime(timezone=True), nullable=True)

    # Restricción: el rol sólo puede ser "user" o "admin".
    __table_args__ = (
        CheckConstraint("rol IN ('user', 'admin')", name="ck_usuario_rol"),
    )

    # Relaciones ORM para navegación entre objetos.
    fichajes  = relationship("Fichaje",  back_populates="usuario", lazy="dynamic")
    alertas   = relationship("Alerta",   back_populates="usuario", lazy="dynamic")
    preavisos = relationship("Preaviso", back_populates="usuario", lazy="dynamic")
    documentos = relationship("Documento", back_populates="usuario", lazy="dynamic")


class Fichaje(Base):
    """
    Evento de fichaje de un empleado (entrada, descanso, comida, salida).
    Almacena el timestamp con zona horaria y las coordenadas GPS.
    """
    __tablename__ = "fichajes"

    id         = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    tipo       = Column(String(20), nullable=False)
    timestamp  = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    latitud    = Column(Float, nullable=True)
    longitud   = Column(Float, nullable=True)
    dentro_zona = Column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint("tipo IN ('entrada','descanso','comida','salida')", name="ck_fichaje_tipo"),
        # Índice compuesto para acelerar consultas de historial por usuario y fecha.
        Index("ix_fichajes_usuario_timestamp", "usuario_id", "timestamp"),
    )

    usuario = relationship("Usuario", back_populates="fichajes")


class Alerta(Base):
    """
    Incidencia generada automáticamente por el sistema
    (p. ej. empleado que no ha fichado en un día laborable).
    """
    __tablename__ = "alertas"

    id         = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    motivo     = Column(String(200), nullable=False)
    fecha      = Column(Date, nullable=False, default=date.today)

    __table_args__ = (
        Index("ix_alertas_usuario_fecha", "usuario_id", "fecha"),
    )

    usuario = relationship("Usuario", back_populates="alertas")


class Preaviso(Base):
    """
    Solicitud de ausencia o retraso enviada por un empleado
    y gestionada (aprobada/rechazada) por el administrador.
    """
    __tablename__ = "preavisos"

    id             = Column(Integer, primary_key=True, index=True)
    usuario_id     = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    tipo           = Column(String(20), nullable=False)          # "retraso" | "falta"
    fecha_ausencia = Column(Date, nullable=False)
    motivo         = Column(String(500), nullable=False)
    estado         = Column(String(20), nullable=False, default="pendiente")  # pendiente | aceptado | rechazado
    visto_admin    = Column(Boolean, default=False)
    visto_usuario  = Column(Boolean, default=False)

    __table_args__ = (
        CheckConstraint("tipo IN ('retraso','falta')", name="ck_preaviso_tipo"),
        CheckConstraint("estado IN ('pendiente','aceptado','rechazado')", name="ck_preaviso_estado"),
        Index("ix_preavisos_usuario", "usuario_id"),
    )

    usuario = relationship("Usuario", back_populates="preavisos")


class Documento(Base):
    """
    Referencia a un documento corporativo almacenado en el servidor FTPS.
    Se registra qué usuario es el destinatario y si lo ha descargado.
    """
    __tablename__ = "documentos"

    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    titulo      = Column(String(200), nullable=False)
    url_destino = Column(String(300), nullable=False)  # Nombre del archivo en el FTPS
    leido       = Column(Boolean, default=False)
    fecha_envio = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    usuario = relationship("Usuario", back_populates="documentos")


class LogAcceso(Base):
    """
    Registro de auditoría de accesos y acciones relevantes del sistema.
    Permite rastrear quién hizo qué y cuándo.
    """
    __tablename__ = "logs_acceso"

    id         = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    accion     = Column(String(100), nullable=False)   # "login", "fichaje", "admin_alta_usuario", etc.
    detalle    = Column(String(500), nullable=True)
    ip         = Column(String(45), nullable=True)     # IPv4 o IPv6
    timestamp  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_logs_timestamp", "timestamp"),
        Index("ix_logs_usuario", "usuario_id"),
    )
