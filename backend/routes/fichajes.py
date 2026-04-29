"""
routes/fichajes.py — Endpoints de fichaje e informes
=====================================================
"""

import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import csv
import io

from models import get_db, Fichaje, Usuario
from schemas import FichajeRequest, FichajeResponse
from services import (
    get_current_user, require_admin, registrar_log,
    registrar_fichaje, resumen_diario, resumen_mensual,
)

router = APIRouter(prefix="/fichajes", tags=["Fichaje"])
logger = logging.getLogger("fichaje.fichajes")


@router.post("/", response_model=FichajeResponse)
def fichar(
    data: FichajeRequest,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Registra un nuevo evento de fichaje (entrada/descanso/comida/salida)
    para el usuario autenticado, con sus coordenadas GPS.
    Valida la secuencia lógica y el geofencing.
    """
    nuevo = registrar_fichaje(current_user.id, data.tipo, data.lat, data.lon, db)
    registrar_log(
        db,
        accion     = "fichaje",
        usuario_id = current_user.id,
        detalle    = f"tipo={data.tipo} lat={data.lat} lon={data.lon} zona={nuevo.dentro_zona}",
    )
    logger.info(f"Fichaje: usuario={current_user.email} tipo={data.tipo} zona={nuevo.dentro_zona}")
    return nuevo


@router.get("/mis_fichajes", response_model=list[FichajeResponse])
def mis_fichajes(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Devuelve el historial completo de fichajes del usuario autenticado."""
    return (
        db.query(Fichaje)
        .filter(Fichaje.usuario_id == current_user.id)
        .order_by(Fichaje.timestamp.desc())
        .all()
    )


@router.get("/resumen_diario")
def obtener_resumen_diario(
    fecha: date = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Devuelve el resumen de horas trabajadas en un día concreto.
    Si no se especifica fecha, usa el día actual.
    """
    if fecha is None:
        fecha = date.today()
    return resumen_diario(current_user.id, fecha, db)


@router.get("/resumen_mensual")
def obtener_resumen_mensual(
    anio: int = None,
    mes: int = None,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Devuelve el resumen mensual: días trabajados, horas totales y faltas.
    Si no se especifican año y mes, usa el mes actual.
    """
    hoy = date.today()
    if anio is None:
        anio = hoy.year
    if mes is None:
        mes = hoy.month
    if not (1 <= mes <= 12):
        raise HTTPException(status_code=422, detail="El mes debe estar entre 1 y 12.")
    return resumen_mensual(current_user.id, anio, mes, db)


@router.get("/exportar_csv")
def exportar_csv(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Genera y descarga un archivo CSV con el historial completo de fichajes
    del usuario autenticado.
    """
    fichajes = (
        db.query(Fichaje)
        .filter(Fichaje.usuario_id == current_user.id)
        .order_by(Fichaje.timestamp)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Tipo", "Fecha", "Hora", "Latitud", "Longitud", "Dentro de zona"])
    for f in fichajes:
        writer.writerow([
            f.tipo,
            f.timestamp.strftime("%d/%m/%Y"),
            f.timestamp.strftime("%H:%M:%S"),
            f.latitud  or "",
            f.longitud or "",
            "Sí" if f.dentro_zona else "No",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=fichajes_{current_user.id}.csv"},
    )


# ── Endpoints de administrador ────────────────────────────────────────────────

@router.get("/estado_empleados")
def estado_empleados(
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """
    Monitor en tiempo real: último estado de cada empleado.
    Usa una única consulta con subconsulta para evitar el problema N+1.
    """
    subquery = (
        db.query(func.max(Fichaje.id).label("max_id"))
        .group_by(Fichaje.usuario_id)
        .subquery()
    )
    resultados = (
        db.query(Usuario, Fichaje)
        .outerjoin(Fichaje, Fichaje.id == subquery.c.max_id)
        .filter(Usuario.rol == "user", Usuario.activo == True)
        .all()
    )
    return [
        {
            "id":            u.id,
            "nombre":        u.nombre,
            "email":         u.email,
            "ultimo_evento": f.tipo if f else "sin_registro",
            "hora":          f.timestamp.strftime("%H:%M") if f else "--:--",
            "en_zona":       f.dentro_zona if f else None,
        }
        for u, f in resultados
    ]


@router.get("/admin/{uid}/historial", response_model=list[FichajeResponse])
def historial_empleado(
    uid: int,
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """Devuelve el historial de fichajes de cualquier empleado. Solo admins."""
    return (
        db.query(Fichaje)
        .filter(Fichaje.usuario_id == uid)
        .order_by(Fichaje.timestamp.desc())
        .all()
    )


@router.get("/admin/{uid}/resumen_mensual")
def resumen_mensual_admin(
    uid: int,
    anio: int = None,
    mes: int = None,
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """Resumen mensual de cualquier empleado. Solo admins."""
    hoy = date.today()
    return resumen_mensual(uid, anio or hoy.year, mes or hoy.month, db)
