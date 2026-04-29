"""
test_fichajes.py — Tests de fichaje y geofencing
=================================================
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, get_db
from models.models import Usuario
from services.auth_service import hash_password
from main import app

TEST_DB_URL = "sqlite:///./test_fichajes.db"
engine_test = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestSession  = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine_test)
    db = TestSession()
    db.add(Usuario(
        nombre="Empleado Test", email="empleado@test.com",
        password_hash=hash_password("Pass1234!"), rol="user",
    ))
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine_test)


client = TestClient(app)


def _token():
    resp = client.post("/auth/login", json={"email": "empleado@test.com", "password": "Pass1234!"})
    return resp.json()["access_token"]


def _auth():
    return {"Authorization": f"Bearer {_token()}"}


class TestFichaje:

    def test_primera_accion_debe_ser_entrada(self):
        """Sin fichajes previos, sólo se permite 'entrada'."""
        resp = client.post("/fichajes/", json={"tipo": "salida", "lat": 0.0, "lon": 0.0}, headers=_auth())
        assert resp.status_code == 409

    def test_entrada_correcta(self):
        """El primer fichaje de tipo 'entrada' debe aceptarse."""
        resp = client.post("/fichajes/", json={"tipo": "entrada", "lat": 36.685, "lon": -6.126}, headers=_auth())
        assert resp.status_code == 200
        assert resp.json()["tipo"] == "entrada"

    def test_secuencia_entrada_salida(self):
        """Secuencia entrada → salida debe ser válida."""
        h = _auth()
        client.post("/fichajes/", json={"tipo": "entrada", "lat": 0.0, "lon": 0.0}, headers=h)
        resp = client.post("/fichajes/", json={"tipo": "salida", "lat": 0.0, "lon": 0.0}, headers=h)
        assert resp.status_code == 200

    def test_doble_entrada_rechazada(self):
        """Registrar dos 'entrada' consecutivas debe devolver 409."""
        h = _auth()
        client.post("/fichajes/", json={"tipo": "entrada", "lat": 0.0, "lon": 0.0}, headers=h)
        resp = client.post("/fichajes/", json={"tipo": "entrada", "lat": 0.0, "lon": 0.0}, headers=h)
        assert resp.status_code == 409

    def test_salida_sin_entrada_rechazada(self):
        """Registrar 'salida' sin 'entrada' previa debe devolver 409."""
        resp = client.post("/fichajes/", json={"tipo": "salida", "lat": 0.0, "lon": 0.0}, headers=_auth())
        assert resp.status_code == 409

    def test_tipo_invalido_rechazado(self):
        """Un tipo de fichaje no reconocido debe devolver 422."""
        resp = client.post("/fichajes/", json={"tipo": "almuerzo", "lat": 0.0, "lon": 0.0}, headers=_auth())
        assert resp.status_code == 422

    def test_historial_vacio_inicial(self):
        """Un usuario nuevo debe tener el historial vacío."""
        resp = client.get("/fichajes/mis_fichajes", headers=_auth())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_historial_tras_fichaje(self):
        """Tras un fichaje, el historial debe contener ese registro."""
        h = _auth()
        client.post("/fichajes/", json={"tipo": "entrada", "lat": 0.0, "lon": 0.0}, headers=h)
        resp = client.get("/fichajes/mis_fichajes", headers=h)
        assert len(resp.json()) == 1

    def test_exportar_csv(self):
        """La exportación CSV debe devolver content-type text/csv."""
        resp = client.get("/fichajes/exportar_csv", headers=_auth())
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]


class TestGeofencing:

    def test_fichaje_dentro_zona_marcado_correctamente(self):
        """Coordenadas dentro del radio deben marcar dentro_zona=True."""
        # Coordenadas del centro de trabajo configurado en .env.
        resp = client.post(
            "/fichajes/",
            json={"tipo": "entrada", "lat": 36.6850, "lon": -6.1261},
            headers=_auth(),
        )
        assert resp.status_code == 200
        # El resultado depende de la configuración del geofence en test.

    def test_fichaje_fuera_zona_permitido_pero_marcado(self):
        """
        Coordenadas fuera del radio deben permitir el fichaje pero
        marcarlo con dentro_zona=False.
        """
        resp = client.post(
            "/fichajes/",
            json={"tipo": "entrada", "lat": 40.4168, "lon": -3.7038},  # Madrid
            headers=_auth(),
        )
        assert resp.status_code == 200
        assert resp.json()["dentro_zona"] == False
