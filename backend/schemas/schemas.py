"""
schemas.py — Esquemas Pydantic de validación
=============================================
Define los contratos de entrada y salida de la API.
Pydantic valida y convierte automáticamente los datos.
"""

from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
import re


# ─────────────────────────────────────────────────────────────────────────────
# AUTENTICACIÓN
# ─────────────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def email_no_vacio(cls, v):
        if not v or not v.strip():
            raise ValueError("El email no puede estar vacío.")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def password_no_vacio(cls, v):
        if not v or len(v) < 1:
            raise ValueError("La contraseña no puede estar vacía.")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    nombre: str
    rol: str


# ─────────────────────────────────────────────────────────────────────────────
# USUARIOS
# ─────────────────────────────────────────────────────────────────────────────

class UsuarioCreate(BaseModel):
    nombre: str
    email: str
    password: str
    rol: str = "user"

    @field_validator("nombre")
    @classmethod
    def nombre_valido(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres.")
        if len(v) > 100:
            raise ValueError("El nombre no puede superar 100 caracteres.")
        return v.strip()

    @field_validator("email")
    @classmethod
    def email_valido(cls, v):
        patron = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
        if not re.match(patron, v):
            raise ValueError("El formato del email no es válido.")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def password_seguro(cls, v):
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return v

    @field_validator("rol")
    @classmethod
    def rol_valido(cls, v):
        if v not in ("user", "admin"):
            raise ValueError("El rol debe ser 'user' o 'admin'.")
        return v


class UsuarioResponse(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str
    activo: bool
    creado_en: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# FICHAJES
# ─────────────────────────────────────────────────────────────────────────────

TIPOS_FICHAJE = ("entrada", "descanso", "comida", "salida")


class FichajeRequest(BaseModel):
    tipo: str
    lat: float
    lon: float

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v):
        if v not in TIPOS_FICHAJE:
            raise ValueError(f"Tipo de fichaje inválido. Opciones: {TIPOS_FICHAJE}")
        return v

    @field_validator("lat")
    @classmethod
    def lat_valida(cls, v):
        if not (-90 <= v <= 90):
            raise ValueError("La latitud debe estar entre -90 y 90.")
        return v

    @field_validator("lon")
    @classmethod
    def lon_valida(cls, v):
        if not (-180 <= v <= 180):
            raise ValueError("La longitud debe estar entre -180 y 180.")
        return v


class FichajeResponse(BaseModel):
    id: int
    tipo: str
    timestamp: datetime
    latitud: Optional[float]
    longitud: Optional[float]
    dentro_zona: bool

    class Config:
        from_attributes = True


class ResumenDiario(BaseModel):
    fecha: str
    horas_trabajadas: float
    fichajes: list


class ResumenMensual(BaseModel):
    mes: str
    total_dias: int
    total_horas: float
    dias_falta: int


# ─────────────────────────────────────────────────────────────────────────────
# PREAVISOS
# ─────────────────────────────────────────────────────────────────────────────

class PreavisoCreate(BaseModel):
    tipo: str
    fecha: date
    motivo: str

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v):
        if v not in ("retraso", "falta"):
            raise ValueError("El tipo debe ser 'retraso' o 'falta'.")
        return v

    @field_validator("motivo")
    @classmethod
    def motivo_valido(cls, v):
        if not v or len(v.strip()) < 5:
            raise ValueError("El motivo debe tener al menos 5 caracteres.")
        if len(v) > 500:
            raise ValueError("El motivo no puede superar 500 caracteres.")
        return v.strip()


class DecisionRequest(BaseModel):
    estado: str

    @field_validator("estado")
    @classmethod
    def estado_valido(cls, v):
        if v not in ("aceptado", "rechazado"):
            raise ValueError("El estado debe ser 'aceptado' o 'rechazado'.")
        return v
