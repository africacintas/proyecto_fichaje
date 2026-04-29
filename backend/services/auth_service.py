"""
auth_service.py — Servicio de autenticación
=============================================
Gestiona la creación y verificación de tokens JWT,
el hash de contraseñas y la protección contra fuerza bruta.
"""

import os
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from models import get_db, Usuario

logger = logging.getLogger("fichaje.auth")

# ── Configuración ─────────────────────────────────────────────────────────────
JWT_SECRET_KEY     = os.getenv("JWT_SECRET_KEY", "dev_secret_change_in_production")
JWT_ALGORITHM      = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))
MAX_ATTEMPTS       = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOCKOUT_MINUTES    = int(os.getenv("LOCKOUT_MINUTES", "15"))

pwd_context   = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ── Hash de contraseñas ───────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Genera el hash bcrypt de una contraseña."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Compara una contraseña en texto plano con su hash almacenado."""
    return pwd_context.verify(plain, hashed)


# ── Tokens JWT ────────────────────────────────────────────────────────────────

def create_access_token(user_id: int, rol: str) -> str:
    """
    Genera un token JWT firmado con user_id, rol y fecha de expiración.
    El token es válido durante JWT_EXPIRE_MINUTES minutos.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"user_id": user_id, "rol": rol, "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decodifica y valida un token JWT.
    Lanza HTTPException 401 si el token es inválido o ha expirado.
    """
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Dependencias de autenticación ─────────────────────────────────────────────

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    """
    Dependencia FastAPI: verifica el token JWT de cada petición y
    devuelve el objeto Usuario autenticado.
    """
    payload = decode_token(token)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido.")

    usuario = db.query(Usuario).filter(Usuario.id == user_id, Usuario.activo == True).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado o desactivado.")
    return usuario


def require_admin(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    """
    Dependencia FastAPI: garantiza que el usuario autenticado tiene rol admin.
    Lanza HTTP 403 en caso contrario.
    """
    if current_user.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acción restringida a administradores.",
        )
    return current_user


# ── Protección contra fuerza bruta ────────────────────────────────────────────

def check_brute_force(usuario: Usuario, db: Session):
    """
    Verifica si el usuario está bloqueado por demasiados intentos fallidos.
    Lanza HTTP 429 con el tiempo restante de bloqueo.
    """
    if not usuario.bloqueado_hasta:
        return

    ahora = datetime.now(timezone.utc)
    if usuario.bloqueado_hasta.tzinfo is None:
        from datetime import timezone as tz
        bloqueado = usuario.bloqueado_hasta.replace(tzinfo=timezone.utc)
    else:
        bloqueado = usuario.bloqueado_hasta

    if ahora < bloqueado:
        restante = int((bloqueado - ahora).total_seconds() / 60) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Cuenta bloqueada por {restante} minuto(s) por demasiados intentos fallidos.",
        )
    else:
        # El bloqueo ha expirado, reiniciar contadores.
        usuario.intentos_login  = 0
        usuario.bloqueado_hasta = None
        db.commit()


def register_failed_attempt(usuario: Usuario, db: Session):
    """
    Incrementa el contador de intentos fallidos.
    Si supera MAX_ATTEMPTS, bloquea la cuenta durante LOCKOUT_MINUTES.
    """
    usuario.intentos_login += 1
    if usuario.intentos_login >= MAX_ATTEMPTS:
        usuario.bloqueado_hasta = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
        logger.warning(f"Cuenta bloqueada por fuerza bruta: {usuario.email}")
    db.commit()


def reset_failed_attempts(usuario: Usuario, db: Session):
    """Reinicia los contadores de intentos fallidos tras un login exitoso."""
    usuario.intentos_login  = 0
    usuario.bloqueado_hasta = None
    db.commit()
