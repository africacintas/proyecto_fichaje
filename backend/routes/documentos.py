"""
routes/documentos.py — Gestión de documentos vía FTPS
======================================================
"""

import os
import io
import logging
from ftplib import FTP, error_perm
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from models import get_db, Documento, Usuario
from services import get_current_user, require_admin, registrar_log

router = APIRouter(prefix="/documentos", tags=["Documentos"])
logger = logging.getLogger("fichaje.documentos")

FTP_HOST = os.getenv("FTP_HOST", "asir_ftps")
FTP_USER = os.getenv("FTP_USER_NAME", "ftpuser")
FTP_PASS = os.getenv("FTP_USER_PASS", "")


def _conectar_ftp() -> FTP:
    """Abre y autentica una conexión al servidor FTPS. Lanza 503 si falla."""
    try:
        ftp = FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        return ftp
    except Exception as e:
        logger.error(f"No se pudo conectar al servidor FTPS: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servidor de documentos no disponible temporalmente.",
        )


@router.post("/")
async def subir_documento(
    usuario_id: int = Form(...),
    titulo: str = Form(...),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin = Depends(require_admin),
):
    """
    Sube un documento al servidor FTPS y registra la referencia en BD.
    El nombre remoto incluye el ID del destinatario como prefijo para
    evitar colisiones entre archivos de distintos usuarios.
    Solo admins.
    """
    if not titulo or len(titulo.strip()) < 2:
        raise HTTPException(status_code=422, detail="El título del documento es obligatorio.")

    destinatario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not destinatario:
        raise HTTPException(status_code=404, detail="Usuario destinatario no encontrado.")

    nombre_remoto = f"{usuario_id}_{archivo.filename}"
    ftp = _conectar_ftp()
    try:
        ftp.storbinary(f"STOR {nombre_remoto}", archivo.file)
    finally:
        ftp.quit()

    db.add(Documento(usuario_id=usuario_id, titulo=titulo.strip(), url_destino=nombre_remoto))
    db.commit()
    registrar_log(db, "documento_enviado", usuario_id=admin.id,
                  detalle=f"destinatario={destinatario.email} titulo={titulo}")
    return {"status": "ok", "mensaje": f"Documento enviado a {destinatario.nombre}."}


@router.get("/mis_documentos")
def mis_documentos(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Lista los documentos asignados al usuario autenticado."""
    return db.query(Documento).filter(Documento.usuario_id == current_user.id).all()


@router.get("/{doc_id}/descargar")
def descargar_documento(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Descarga un documento desde el FTPS.
    Solo el destinatario o un admin puede acceder.
    Marca el documento como leído tras la descarga.
    """
    doc = db.query(Documento).filter(Documento.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    if doc.usuario_id != current_user.id and current_user.rol != "admin":
        raise HTTPException(status_code=403, detail="Sin permiso para acceder a este documento.")

    ftp    = _conectar_ftp()
    buffer = io.BytesIO()
    try:
        ftp.retrbinary(f"RETR {doc.url_destino}", buffer.write)
    except error_perm:
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor.")
    finally:
        ftp.quit()

    if doc.usuario_id == current_user.id:
        doc.leido = True
        db.commit()

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={doc.url_destino}"},
    )


@router.get("/admin/todos")
def admin_listar_documentos(
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """Lista todos los documentos del sistema con estado de lectura. Solo admins."""
    resultados = db.query(Documento, Usuario.nombre).join(Usuario).all()
    return [
        {
            "id":             d.id,
            "titulo":         d.titulo,
            "leido":          d.leido,
            "usuario_nombre": nombre,
            "fecha_envio":    d.fecha_envio.isoformat(),
        }
        for d, nombre in resultados
    ]
