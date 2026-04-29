"""
seed.py — Script de datos de prueba
=====================================
Genera los mismos usuarios, fichajes, alertas y preavisos
que existían en el proyecto original, adaptados al nuevo esquema.

Usuarios creados:
  - admin@asir.com       (admin)   contraseña: 1234
  - juan.perez@asir.com  (user)    contraseña: 1234
  - maria.garcia@asir.com(user)    contraseña: 1234
  - carlos.sanchez@asir.com(user)  contraseña: 1234
  - laura.rodriguez@asir.com(user) contraseña: 1234

Uso:
  docker exec asir_backend python seed.py
  (o se ejecuta automáticamente en el arranque si SEED_DATA=true)
"""

import os
import random
import time
from datetime import datetime, date, timedelta, time as dt_time, timezone

from sqlalchemy.exc import OperationalError
from passlib.context import CryptContext

# Importar modelos y sesión del proyecto
from models.database import SessionLocal, engine, Base
from models.models import Usuario, Fichaje, Alerta, Preaviso

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Coordenadas del centro de trabajo (Jerez de la Frontera) ─────────────────
JEREZ_LAT = 36.68
JEREZ_LON = -6.12

# ── Usuarios de prueba (idénticos al proyecto original) ──────────────────────
USUARIOS_PRUEBA = [
    {"nombre": "Juan Pérez",      "email": "juan.perez@asir.com"},
    {"nombre": "María García",    "email": "maria.garcia@asir.com"},
    {"nombre": "Carlos Sánchez",  "email": "carlos.sanchez@asir.com"},
    {"nombre": "Laura Rodríguez", "email": "laura.rodriguez@asir.com"},
]

ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL",    "admin@asir.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")
ADMIN_NOMBRE   = os.getenv("ADMIN_NOMBRE",   "ASIR Admin")


def _jitter_coords(base_lat: float, base_lon: float, delta: float = 0.01):
    """Añade variación aleatoria pequeña a las coordenadas para simular realismo."""
    return (
        base_lat + random.uniform(-delta, delta),
        base_lon + random.uniform(-delta, delta),
    )


def _ts(dia: date, hora: int, minuto: int, offset_min: int = 0) -> datetime:
    """Crea un datetime con zona horaria UTC para un día y hora dados."""
    return datetime.combine(
        dia,
        dt_time(hora, minuto),
        tzinfo=timezone.utc,
    ) + timedelta(minutes=offset_min)


def seed():
    """
    Inserta los datos de prueba en la base de datos.
    Es idempotente: si los usuarios ya existen no los vuelve a crear.
    """

    # Esperar a que la BD esté disponible (útil si se ejecuta justo al arrancar).
    for intento in range(5):
        try:
            Base.metadata.create_all(bind=engine)
            break
        except OperationalError:
            print(f"BD no disponible, reintentando... ({intento + 1}/5)")
            time.sleep(5)

    db = SessionLocal()

    try:
        # ── Administrador ─────────────────────────────────────────────────────
        if not db.query(Usuario).filter(Usuario.email == ADMIN_EMAIL).first():
            db.add(Usuario(
                nombre        = ADMIN_NOMBRE,
                email         = ADMIN_EMAIL,
                password_hash = pwd_context.hash(ADMIN_PASSWORD),
                rol           = "admin",
            ))
            db.commit()
            print(f"✅ Admin creado: {ADMIN_EMAIL}")
        else:
            print(f"ℹ️  Admin ya existe: {ADMIN_EMAIL}")

        # ── Comprobar si los datos de prueba ya existen ───────────────────────
        if db.query(Usuario).filter(Usuario.email == USUARIOS_PRUEBA[0]["email"]).first():
            print("ℹ️  Los datos de prueba ya existen. No se vuelven a crear.")
            return

        print("🌱 Creando datos de prueba...")

        password_hash = pwd_context.hash("1234")
        hoy           = date.today()

        for user_data in USUARIOS_PRUEBA:
            # ── Crear usuario ─────────────────────────────────────────────────
            usuario = Usuario(
                nombre        = user_data["nombre"],
                email         = user_data["email"],
                password_hash = password_hash,
                rol           = "user",
            )
            db.add(usuario)
            db.flush()  # Obtener el ID asignado antes de crear los fichajes

            print(f"  👤 {user_data['nombre']} ({user_data['email']})")

            # ── Generar historial de los últimos 30 días laborables ───────────
            for i in range(30):
                dia = hoy - timedelta(days=i)

                # Saltar fines de semana
                if dia.weekday() >= 5:
                    continue

                # 5% de probabilidad de falta
                if random.random() < 0.05:
                    db.add(Alerta(
                        usuario_id = usuario.id,
                        motivo     = "Falta injustificada",
                        fecha      = dia,
                    ))
                    if random.random() < 0.5:
                        db.add(Preaviso(
                            usuario_id     = usuario.id,
                            tipo           = "falta",
                            fecha_ausencia = dia,
                            motivo         = "Asuntos personales.",
                            estado         = random.choice(["aceptado", "rechazado"]),
                        ))
                    continue  # No hay fichajes este día

                # ── Entrada: entre 08:45 y 09:30 ─────────────────────────────
                offset_entrada = random.randint(-15, 30)
                hora_entrada   = _ts(dia, 9, 0, offset_entrada)
                lat, lon       = _jitter_coords(JEREZ_LAT, JEREZ_LON)
                db.add(Fichaje(
                    usuario_id  = usuario.id,
                    tipo        = "entrada",
                    timestamp   = hora_entrada,
                    latitud     = lat,
                    longitud    = lon,
                    dentro_zona = True,
                ))

                # Alerta de retraso si llega después de las 09:15
                if hora_entrada.minute > 15 and hora_entrada.hour == 9:
                    db.add(Alerta(
                        usuario_id = usuario.id,
                        motivo     = "Retraso",
                        fecha      = dia,
                    ))
                    if random.random() < 0.3:
                        db.add(Preaviso(
                            usuario_id     = usuario.id,
                            tipo           = "retraso",
                            fecha_ausencia = dia,
                            motivo         = "Atasco en la entrada a Jerez.",
                            estado         = "pendiente",
                        ))

                # ── Descanso matutino (70% de los días) ──────────────────────
                if random.random() < 0.7:
                    hora_desc_ini = _ts(dia, 11, 0, random.randint(0, 30))
                    hora_desc_fin = hora_desc_ini + timedelta(minutes=random.randint(15, 25))
                    db.add(Fichaje(usuario_id=usuario.id, tipo="descanso",
                                   timestamp=hora_desc_ini, latitud=JEREZ_LAT, longitud=JEREZ_LON, dentro_zona=True))
                    db.add(Fichaje(usuario_id=usuario.id, tipo="entrada",
                                   timestamp=hora_desc_fin, latitud=JEREZ_LAT, longitud=JEREZ_LON, dentro_zona=True))

                # ── Comida: entre 13:45 y 14:15, duración 55–75 min ──────────
                hora_comida_ini = _ts(dia, 14, 0, random.randint(-15, 15))
                hora_comida_fin = hora_comida_ini + timedelta(hours=1, minutes=random.randint(-5, 15))
                db.add(Fichaje(usuario_id=usuario.id, tipo="comida",
                               timestamp=hora_comida_ini, latitud=JEREZ_LAT, longitud=JEREZ_LON, dentro_zona=True))
                db.add(Fichaje(usuario_id=usuario.id, tipo="entrada",
                               timestamp=hora_comida_fin, latitud=JEREZ_LAT, longitud=JEREZ_LON, dentro_zona=True))

                # ── Salida: entre 17:30 y 18:30 ──────────────────────────────
                hora_salida = _ts(dia, 18, 0, random.randint(-30, 30))
                lat, lon    = _jitter_coords(JEREZ_LAT, JEREZ_LON)
                db.add(Fichaje(
                    usuario_id  = usuario.id,
                    tipo        = "salida",
                    timestamp   = hora_salida,
                    latitud     = lat,
                    longitud    = lon,
                    dentro_zona = True,
                ))

        db.flush()

        # ── Preavisos pendientes fijos (para demostración en panel admin) ─────
        usuarios_creados = db.query(Usuario).filter(
            Usuario.email.in_([u["email"] for u in USUARIOS_PRUEBA])
        ).all()

        if len(usuarios_creados) >= 3:
            db.add(Preaviso(
                usuario_id     = usuarios_creados[0].id,
                tipo           = "retraso",
                fecha_ausencia = hoy + timedelta(days=2),
                motivo         = "Cita médica a primera hora. Llegaré en cuanto pueda.",
                estado         = "pendiente",
            ))
            db.add(Preaviso(
                usuario_id     = usuarios_creados[1].id,
                tipo           = "falta",
                fecha_ausencia = hoy + timedelta(days=10),
                motivo         = "Día de asuntos propios.",
                estado         = "pendiente",
            ))
            db.add(Preaviso(
                usuario_id     = usuarios_creados[2].id,
                tipo           = "falta",
                fecha_ausencia = hoy + timedelta(days=5),
                motivo         = "Gestiones personales que no puedo posponer.",
                estado         = "pendiente",
            ))

        db.commit()
        print("\n✅ Datos de prueba creados correctamente.")
        print("\n📋 Credenciales de acceso:")
        print(f"   Admin : {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        for u in USUARIOS_PRUEBA:
            print(f"   User  : {u['email']} / 1234")

    except Exception as e:
        db.rollback()
        print(f"❌ Error al crear los datos de prueba: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
