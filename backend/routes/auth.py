"""
routes/auth.py — Endpoints de autenticación
============================================
"""

import logging
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from models import get_db, Usuario
from schemas import LoginRequest, TokenResponse
from services import (
    verify_password, create_access_token,
    check_brute_force, register_failed_attempt, reset_failed_attempts,
    registrar_log,
)
from fastapi import HTTPException, status

router = APIRouter(prefix="/auth", tags=["Autenticación"])
logger = logging.getLogger("fichaje.auth")


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """
    Autentica al usuario con email y contraseña.
    Incorpora protección contra fuerza bruta: bloquea la cuenta
    tras MAX_LOGIN_ATTEMPTS intentos fallidos consecutivos.
    Devuelve un token JWT válido para las siguientes peticiones.
    """
    ip = request.client.host if request.client else "desconocida"

    usuario = db.query(Usuario).filter(
        Usuario.email == data.email,
        Usuario.activo == True,
    ).first()

    # Verificar bloqueo por intentos previos (si el usuario existe).
    if usuario:
        check_brute_force(usuario, db)

    # Credenciales incorrectas.
    if not usuario or not verify_password(data.password, usuario.password_hash):
        if usuario:
            register_failed_attempt(usuario, db)
            logger.warning(f"Login fallido para {data.email} desde {ip} — intento {usuario.intentos_login}")
        registrar_log(db, "login_fallido", detalle=data.email, ip=ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos.",
        )

    # Login correcto: reiniciar contadores y emitir token.
    reset_failed_attempts(usuario, db)
    token = create_access_token(usuario.id, usuario.rol)
    registrar_log(db, "login_ok", usuario_id=usuario.id, ip=ip)
    logger.info(f"Login correcto: {usuario.email} ({usuario.rol}) desde {ip}")

    return TokenResponse(
        access_token=token,
        user_id=usuario.id,
        nombre=usuario.nombre,
        rol=usuario.rol,
    )
