"""
routes/usuarios.py — Endpoints de gestión de usuarios
======================================================
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import get_db, Usuario
from schemas import UsuarioCreate, UsuarioResponse
from services import hash_password, require_admin, registrar_log

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])
logger = logging.getLogger("fichaje.usuarios")


@router.post("/", response_model=UsuarioResponse)
def crear_usuario(
    data: UsuarioCreate,
    db: Session = Depends(get_db),
    admin = Depends(require_admin),
):
    """
    Registra un nuevo empleado o administrador.
    Sólo accesible para administradores.
    Devuelve HTTP 400 si ya existe un usuario con ese email.
    """
    try:
        nuevo = Usuario(
            nombre        = data.nombre,
            email         = data.email,
            password_hash = hash_password(data.password),
            rol           = data.rol,
        )
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
        registrar_log(db, "alta_usuario", usuario_id=admin.id, detalle=f"Nuevo usuario: {data.email}")
        logger.info(f"Usuario creado: {data.email} por admin {admin.email}")
        return nuevo
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese email.",
        )


@router.get("/", response_model=list[UsuarioResponse])
def listar_usuarios(
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """Devuelve la lista de todos los usuarios. Sólo para administradores."""
    return db.query(Usuario).order_by(Usuario.nombre).all()


@router.get("/me", response_model=UsuarioResponse)
def mi_perfil(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(__import__("services.auth_service", fromlist=["get_current_user"]).get_current_user),
):
    """Devuelve el perfil del usuario autenticado."""
    return current_user


@router.put("/{uid}/desactivar")
def desactivar_usuario(
    uid: int,
    db: Session = Depends(get_db),
    admin = Depends(require_admin),
):
    """
    Desactiva un usuario (baja lógica, no se borra de la BD).
    Sólo para administradores. No se puede desactivar el propio admin.
    """
    if uid == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No puedes desactivar tu propia cuenta.",
        )
    usuario = db.query(Usuario).filter(Usuario.id == uid).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    usuario.activo = False
    db.commit()
    registrar_log(db, "baja_usuario", usuario_id=admin.id, detalle=f"Desactivado: {usuario.email}")
    return {"status": "ok", "mensaje": f"Usuario {usuario.nombre} desactivado."}


@router.put("/{uid}/activar")
def activar_usuario(
    uid: int,
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """Reactiva un usuario previamente desactivado. Sólo para administradores."""
    usuario = db.query(Usuario).filter(Usuario.id == uid).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    usuario.activo = True
    db.commit()
    return {"status": "ok", "mensaje": f"Usuario {usuario.nombre} reactivado."}
