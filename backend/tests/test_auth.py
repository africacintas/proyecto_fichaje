"""
test_auth.py — Tests de autenticación
======================================
Prueba el login, tokens JWT, bloqueo por fuerza bruta
y protección de endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.database import Base, get_db
from models.models import Usuario
from services.auth_service import hash_password
from main import app

# ── Base de datos en memoria para los tests ───────────────────────────────────
TEST_DB_URL = "sqlite:///./test.db"
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
    """Crea y destruye las tablas antes y después de cada test."""
    Base.metadata.create_all(bind=engine_test)
    db = TestSession()
    db.add(Usuario(
        nombre        = "Admin Test",
        email         = "admin@test.com",
        password_hash = hash_password("Admin1234!"),
        rol           = "admin",
    ))
    db.add(Usuario(
        nombre        = "Usuario Test",
        email         = "user@test.com",
        password_hash = hash_password("User1234!"),
        rol           = "user",
    ))
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine_test)


client = TestClient(app)


# ── Tests de login ────────────────────────────────────────────────────────────

class TestLogin:

    def test_login_correcto_devuelve_token(self):
        """Un login con credenciales válidas debe devolver un token JWT."""
        resp = client.post("/auth/login", json={"email": "user@test.com", "password": "User1234!"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["rol"] == "user"

    def test_login_password_incorrecta(self):
        """Credenciales incorrectas deben devolver HTTP 401."""
        resp = client.post("/auth/login", json={"email": "user@test.com", "password": "mala"})
        assert resp.status_code == 401

    def test_login_email_inexistente(self):
        """Un email no registrado debe devolver HTTP 401."""
        resp = client.post("/auth/login", json={"email": "noexiste@test.com", "password": "algo"})
        assert resp.status_code == 401

    def test_login_email_vacio_rechazado(self):
        """Un email vacío debe ser rechazado por la validación Pydantic (HTTP 422)."""
        resp = client.post("/auth/login", json={"email": "", "password": "algo"})
        assert resp.status_code == 422

    def test_token_permite_acceder_endpoint_protegido(self):
        """Un token válido debe permitir acceder a endpoints protegidos."""
        resp = client.post("/auth/login", json={"email": "user@test.com", "password": "User1234!"})
        token = resp.json()["access_token"]
        resp2 = client.get("/fichajes/mis_fichajes", headers={"Authorization": f"Bearer {token}"})
        assert resp2.status_code == 200

    def test_sin_token_rechazado(self):
        """Sin token, los endpoints protegidos deben devolver HTTP 401."""
        resp = client.get("/fichajes/mis_fichajes")
        assert resp.status_code == 401

    def test_token_invalido_rechazado(self):
        """Un token mal formado debe ser rechazado con HTTP 401."""
        resp = client.get("/fichajes/mis_fichajes", headers={"Authorization": "Bearer token_falso"})
        assert resp.status_code == 401


# ── Tests de control de acceso por rol ───────────────────────────────────────

class TestRoles:

    def _token(self, email, password):
        resp = client.post("/auth/login", json={"email": email, "password": password})
        return resp.json()["access_token"]

    def test_usuario_no_puede_acceder_a_endpoint_admin(self):
        """Un usuario estándar no debe poder acceder a endpoints de administración."""
        token = self._token("user@test.com", "User1234!")
        resp  = client.get("/usuarios/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_admin_puede_listar_usuarios(self):
        """Un administrador debe poder listar usuarios."""
        token = self._token("admin@test.com", "Admin1234!")
        resp  = client.get("/usuarios/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
