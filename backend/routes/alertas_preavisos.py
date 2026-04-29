"""
routes/alertas_preavisos.py — Alertas y preavisos
==================================================
"""

import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from models import get_db, Alerta, Preaviso, Usuario, Fichaje
from schemas import PreavisoCreate, DecisionRequest
from services import get_current_user, require_admin, registrar_log

router = APIRouter(tags=["Alertas y Preavisos"])
logger = logging.getLogger("fichaje.alertas")


# ─────────────────────────────────────────────────────────────────────────────
# ALERTAS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/alertas/generar")
def generar_alertas(
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """
    Genera alertas de falta para empleados que no han fichado hoy.
    Solo se ejecuta en días laborables (lunes–viernes).
    Evita duplicados comprobando si ya existe alerta para ese usuario y fecha.
    """
    hoy = date.today()
    if hoy.weekday() >= 5:
        return {"mensaje": "Es fin de semana, no se generan alertas."}

    usuarios = db.query(Usuario).filter(Usuario.rol == "user", Usuario.activo == True).all()
    nuevas   = 0

    for usuario in usuarios:
        tiene_fichaje = db.query(Fichaje).filter(
            Fichaje.usuario_id == usuario.id,
            func.date(Fichaje.timestamp) == hoy,
        ).first()

        if not tiene_fichaje:
            # Comprobar si ya existe una alerta de falta para hoy.
            ya_existe = db.query(Alerta).filter(
                Alerta.usuario_id == usuario.id,
                Alerta.fecha      == hoy,
                Alerta.motivo     == "Falta",
            ).first()
            if not ya_existe:
                db.add(Alerta(usuario_id=usuario.id, motivo="Falta", fecha=hoy))
                nuevas += 1

    db.commit()
    logger.info(f"Alertas generadas: {nuevas} nuevas para {hoy}")
    return {"nuevas_alertas": nuevas, "fecha": hoy.isoformat()}


@router.get("/alertas/mis_alertas")
def mis_alertas(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Devuelve el historial de alertas del usuario autenticado."""
    return (
        db.query(Alerta)
        .filter(Alerta.usuario_id == current_user.id)
        .order_by(Alerta.fecha.desc())
        .all()
    )


@router.get("/alertas/admin/{uid}")
def alertas_empleado(
    uid: int,
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """Historial de alertas de un empleado concreto. Solo admins."""
    return (
        db.query(Alerta)
        .filter(Alerta.usuario_id == uid)
        .order_by(Alerta.fecha.desc())
        .all()
    )


# ─────────────────────────────────────────────────────────────────────────────
# PREAVISOS
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/preavisos/")
def crear_preaviso(
    data: PreavisoCreate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Registra una solicitud de ausencia o retraso.
    La fecha de ausencia debe ser estrictamente futura.
    """
    if data.fecha <= date.today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La fecha de ausencia debe ser posterior a hoy.",
        )
    db.add(Preaviso(
        usuario_id     = current_user.id,
        tipo           = data.tipo,
        fecha_ausencia = data.fecha,
        motivo         = data.motivo,
    ))
    db.commit()
    registrar_log(db, "preaviso_enviado", usuario_id=current_user.id,
                  detalle=f"tipo={data.tipo} fecha={data.fecha}")
    return {"status": "ok", "mensaje": "Solicitud enviada correctamente."}


@router.get("/preavisos/mis_preavisos")
def mis_preavisos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Devuelve todos los preavisos del usuario autenticado."""
    return (
        db.query(Preaviso)
        .filter(Preaviso.usuario_id == current_user.id)
        .order_by(Preaviso.fecha_ausencia.desc())
        .all()
    )


@router.post("/preavisos/{pid}/marcar_visto")
def marcar_visto(
    pid: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Marca un preaviso como visto por el usuario destinatario."""
    preaviso = db.query(Preaviso).filter(
        Preaviso.id        == pid,
        Preaviso.usuario_id == current_user.id,
    ).first()
    if not preaviso:
        raise HTTPException(status_code=404, detail="Preaviso no encontrado.")
    preaviso.visto_usuario = True
    db.commit()
    return {"status": "ok"}


@router.get("/admin/preavisos/")
def admin_listar_preavisos(
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """Lista todos los preavisos con nombre del empleado. Solo admins."""
    resultados = db.query(Preaviso, Usuario.nombre).join(Usuario).all()
    return [
        {
            "id":             p.id,
            "usuario_nombre": nombre,
            "tipo":           p.tipo,
            "fecha_ausencia": p.fecha_ausencia.isoformat(),
            "motivo":         p.motivo,
            "estado":         p.estado,
        }
        for p, nombre in resultados
    ]


@router.post("/admin/preavisos/{pid}/decidir")
def decidir_preaviso(
    pid: int,
    data: DecisionRequest,
    db: Session = Depends(get_db),
    admin = Depends(require_admin),
):
    """Aprueba o rechaza un preaviso pendiente. Solo admins."""
    preaviso = db.query(Preaviso).filter(Preaviso.id == pid).first()
    if not preaviso:
        raise HTTPException(status_code=404, detail="Preaviso no encontrado.")
    preaviso.estado      = data.estado
    preaviso.visto_admin = True
    db.commit()
    registrar_log(db, f"preaviso_{data.estado}", usuario_id=admin.id, detalle=f"preaviso_id={pid}")
    return {"status": "ok", "nuevo_estado": data.estado}
