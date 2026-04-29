"""
fichaje_service.py — Lógica de negocio de fichajes
====================================================
Gestiona la validación de secuencias, el geofencing,
el cálculo de horas trabajadas y los resúmenes diarios/mensuales.
"""

import os
import math
import logging
from datetime import datetime, date, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from models import Fichaje, Usuario

logger = logging.getLogger("fichaje.fichajes")

# ── Configuración de geofencing ───────────────────────────────────────────────
GEOFENCE_LAT    = float(os.getenv("GEOFENCE_LAT", "36.6850"))
GEOFENCE_LON    = float(os.getenv("GEOFENCE_LON", "-6.1261"))
GEOFENCE_RADIUS = float(os.getenv("GEOFENCE_RADIUS_METERS", "300"))

# Secuencia de fichajes permitida según el estado actual del empleado.
SECUENCIAS_VALIDAS: dict[Optional[str], list[str]] = {
    None:       ["entrada"],
    "entrada":  ["descanso", "comida", "salida"],
    "descanso": ["entrada"],
    "comida":   ["entrada"],
    "salida":   ["entrada"],
}


# ── Geofencing ────────────────────────────────────────────────────────────────

def calcular_distancia_metros(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcula la distancia en metros entre dos coordenadas GPS usando
    la fórmula de Haversine, que tiene en cuenta la curvatura de la Tierra.
    """
    R = 6_371_000  # Radio de la Tierra en metros
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi       = math.radians(lat2 - lat1)
    dlambda    = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def esta_dentro_zona(lat: float, lon: float) -> bool:
    """
    Devuelve True si las coordenadas están dentro del radio de la zona
    de fichaje permitida configurada en las variables de entorno.
    """
    if lat == 0.0 and lon == 0.0:
        return False
    distancia = calcular_distancia_metros(lat, lon, GEOFENCE_LAT, GEOFENCE_LON)
    return distancia <= GEOFENCE_RADIUS


# ── Secuencia de fichajes ─────────────────────────────────────────────────────

def obtener_ultimo_fichaje(usuario_id: int, db: Session) -> Optional[Fichaje]:
    """Devuelve el fichaje más reciente del empleado o None si no tiene ninguno."""
    return (
        db.query(Fichaje)
        .filter(Fichaje.usuario_id == usuario_id)
        .order_by(Fichaje.timestamp.desc())
        .first()
    )


def validar_secuencia(tipo: str, ultimo: Optional[Fichaje]):
    """
    Verifica que el tipo de fichaje solicitado es coherente con el último
    evento registrado. Lanza HTTP 409 si la secuencia no es válida.

    Ejemplos válidos:   None → entrada, entrada → salida
    Ejemplos inválidos: None → salida,  salida  → salida
    """
    ultimo_tipo = ultimo.tipo if ultimo else None
    permitidos  = SECUENCIAS_VALIDAS.get(ultimo_tipo, [])

    if tipo not in permitidos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No es posible registrar '{tipo}' tras '{ultimo_tipo}'. "
                f"Fichajes permitidos ahora: {permitidos}."
            ),
        )


def registrar_fichaje(usuario_id: int, tipo: str, lat: float, lon: float, db: Session) -> Fichaje:
    """
    Valida la secuencia, comprueba el geofencing y registra el fichaje.
    Si las coordenadas son (0,0) se permite el fichaje pero se marca fuera de zona.
    """
    ultimo       = obtener_ultimo_fichaje(usuario_id, db)
    validar_secuencia(tipo, ultimo)

    dentro       = esta_dentro_zona(lat, lon)
    nuevo_fichaje = Fichaje(
        usuario_id  = usuario_id,
        tipo        = tipo,
        latitud     = lat,
        longitud    = lon,
        dentro_zona = dentro,
    )
    db.add(nuevo_fichaje)
    db.commit()
    db.refresh(nuevo_fichaje)

    if not dentro and lat != 0.0:
        distancia = calcular_distancia_metros(lat, lon, GEOFENCE_LAT, GEOFENCE_LON)
        logger.warning(
            f"Fichaje fuera de zona — usuario_id={usuario_id} tipo={tipo} "
            f"distancia={distancia:.0f}m"
        )

    return nuevo_fichaje


# ── Cálculo de horas trabajadas ───────────────────────────────────────────────

def calcular_horas_trabajadas(fichajes: list) -> float:
    """
    Calcula las horas trabajadas a partir de una lista de fichajes ordenados.
    Solo cuenta el tiempo entre 'entrada' y el siguiente 'descanso'/'comida'/'salida'.
    Devuelve el total de horas con dos decimales.
    """
    horas_total = 0.0
    entrada_ts  = None

    for f in sorted(fichajes, key=lambda x: x.timestamp):
        if f.tipo == "entrada":
            entrada_ts = f.timestamp
        elif f.tipo in ("descanso", "comida", "salida") and entrada_ts:
            delta       = (f.timestamp - entrada_ts).total_seconds()
            horas_total += delta / 3600
            entrada_ts  = None

    return round(horas_total, 2)


def resumen_diario(usuario_id: int, fecha: date, db: Session) -> dict:
    """
    Genera el resumen de horas trabajadas por el empleado en un día concreto.
    Incluye la lista de fichajes y el total de horas.
    """
    inicio = datetime.combine(fecha, datetime.min.time()).replace(tzinfo=timezone.utc)
    fin    = inicio + timedelta(days=1)

    fichajes = (
        db.query(Fichaje)
        .filter(
            Fichaje.usuario_id == usuario_id,
            Fichaje.timestamp >= inicio,
            Fichaje.timestamp < fin,
        )
        .order_by(Fichaje.timestamp)
        .all()
    )

    horas = calcular_horas_trabajadas(fichajes)
    return {
        "fecha":            fecha.isoformat(),
        "horas_trabajadas": horas,
        "fichajes": [
            {
                "tipo":      f.tipo,
                "hora":      f.timestamp.strftime("%H:%M:%S"),
                "lat":       f.latitud,
                "lon":       f.longitud,
                "en_zona":   f.dentro_zona,
            }
            for f in fichajes
        ],
    }


def resumen_mensual(usuario_id: int, anio: int, mes: int, db: Session) -> dict:
    """
    Genera el resumen mensual de un empleado:
    días trabajados, horas totales y días con falta.
    """
    primer_dia = date(anio, mes, 1)
    if mes == 12:
        ultimo_dia = date(anio + 1, 1, 1)
    else:
        ultimo_dia = date(anio, mes + 1, 1)

    inicio = datetime.combine(primer_dia, datetime.min.time()).replace(tzinfo=timezone.utc)
    fin    = datetime.combine(ultimo_dia, datetime.min.time()).replace(tzinfo=timezone.utc)

    fichajes = (
        db.query(Fichaje)
        .filter(
            Fichaje.usuario_id == usuario_id,
            Fichaje.timestamp >= inicio,
            Fichaje.timestamp < fin,
        )
        .order_by(Fichaje.timestamp)
        .all()
    )

    # Agrupar fichajes por día.
    dias_con_fichaje: set[date] = set()
    fichajes_por_dia: dict[date, list] = {}
    for f in fichajes:
        d = f.timestamp.date()
        dias_con_fichaje.add(d)
        fichajes_por_dia.setdefault(d, []).append(f)

    # Calcular horas totales sumando las de cada día.
    total_horas = sum(
        calcular_horas_trabajadas(lista)
        for lista in fichajes_por_dia.values()
    )

    # Días laborables del mes (lunes–viernes) sin fichaje = faltas.
    dia_actual   = primer_dia
    dias_laborables = 0
    while dia_actual < ultimo_dia:
        if dia_actual.weekday() < 5:
            dias_laborables += 1
        dia_actual += timedelta(days=1)

    dias_falta = max(0, dias_laborables - len(dias_con_fichaje))

    return {
        "mes":          f"{anio}-{mes:02d}",
        "total_dias":   len(dias_con_fichaje),
        "total_horas":  round(total_horas, 2),
        "dias_laborables": dias_laborables,
        "dias_falta":   dias_falta,
    }
