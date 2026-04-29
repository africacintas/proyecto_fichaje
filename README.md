# Sistema de Control de Presencia con Geolocalización GPS
### Trabajo de Fin de Grado — ASIR

---

## Descripción

Sistema web de control de jornada laboral que registra entradas, pausas y salidas de empleados junto con su geolocalización GPS. Incluye panel de administración, informes de horas, gestión de ausencias y distribución de documentos corporativos.

Cumple con el **Real Decreto-Ley 8/2019** de registro de jornada laboral.

---

## Arquitectura

```
[Navegador]
    │  HTTPS :443 / HTTP :80
    ▼
[Nginx — Proxy inverso]
    │                      │
    ▼ :8501                ▼ :8000
[Frontend              [Backend
 Streamlit]             FastAPI]
                            │
              ┌─────────────┼──────────────┐
              ▼             ▼              ▼
         [PostgreSQL]   [FTPS Server]  [Adminer]
           :5432            :21          :8080

Todos los servicios comparten la red interna 'asir_network'.
```

## Tecnologías

| Componente | Tecnología | Justificación |
|------------|-----------|---------------|
| Backend    | FastAPI (Python 3.11) | Alto rendimiento, documentación automática (Swagger), validación con Pydantic |
| Base de datos | PostgreSQL 15 | SGBD relacional robusto, soporte ACID, índices eficientes |
| ORM        | SQLAlchemy 2.x | Abstracción BD, soporte migraciones con Alembic |
| Frontend   | Streamlit | Desarrollo rápido de interfaces de datos en Python puro |
| Auth       | JWT (python-jose) | Estándar de la industria para autenticación stateless |
| Seguridad  | bcrypt (passlib) | Hash de contraseñas con factor de coste configurable |
| Despliegue | Docker + Compose | Aislamiento, reproducibilidad, despliegue en cualquier servidor |
| HTTPS      | Nginx + TLS | Cifrado en tránsito, proxy inverso |
| Documentos | Pure-FTPd (FTPS) | Demostración del protocolo FTP/FTPS del ciclo ASIR |

---

## Estructura del proyecto

```
proyecto-fichaje/
├── backend/
│   ├── main.py                    # Punto de entrada FastAPI
│   ├── models/
│   │   ├── database.py            # Conexión SQLAlchemy
│   │   └── models.py              # Modelos ORM con índices y restricciones
│   ├── schemas/
│   │   └── schemas.py             # Validación Pydantic de entrada/salida
│   ├── services/
│   │   ├── auth_service.py        # JWT, bcrypt, fuerza bruta
│   │   ├── fichaje_service.py     # Geofencing, horas trabajadas, resúmenes
│   │   └── log_service.py         # Logging y auditoría
│   ├── routes/
│   │   ├── auth.py                # POST /auth/login
│   │   ├── usuarios.py            # CRUD de usuarios
│   │   ├── fichajes.py            # Fichaje, historial, CSV, informes
│   │   ├── alertas_preavisos.py   # Alertas automáticas y solicitudes
│   │   └── documentos.py          # Gestión FTPS
│   ├── tests/
│   │   ├── test_auth.py           # Tests de autenticación y roles
│   │   └── test_fichajes.py       # Tests de fichaje y geofencing
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app.py                     # Interfaz Streamlit completa
│   ├── requirements.txt
│   └── Dockerfile
├── nginx/
│   └── nginx.conf                 # Proxy inverso con HTTPS
├── docker-compose.yml
├── .env.example                   # Plantilla de variables de entorno
├── .gitignore
└── README.md
```

---

## Instalación y despliegue

### Requisitos previos
- Docker Engine 24+
- Docker Compose 2.x
- Git
- OpenSSL

### 1. Clonar el repositorio
```bash
git clone https://github.com/usuario/proyecto-fichaje.git
cd proyecto-fichaje
```

### 2. Configurar variables de entorno
```bash
cp .env.example .env
nano .env   # Editar con valores reales
```

### 3. Generar certificados TLS (para HTTPS y FTPS)
```bash
# Certificado para Nginx (HTTPS)
mkdir -p nginx/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/certs/key.pem -out nginx/certs/cert.pem

# Certificado para Pure-FTPd (FTPS)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout pure-ftpd.pem -out pure-ftpd.pem
```

### 4. Levantar todos los servicios
```bash
docker-compose up -d --build
```

### 5. Verificar el estado
```bash
docker-compose ps
```

### 6. Acceder a la aplicación

| Servicio | URL |
|---------|-----|
| 🌐 Aplicación web | https://localhost |
| 📖 API Swagger | http://localhost:8000/docs |
| 🗄️ Adminer (BD) | http://localhost:8080 |

---

## Ejecutar tests

```bash
docker exec asir_backend pytest tests/ -v
```

---

## Ver logs en tiempo real

```bash
# Todos los servicios
docker-compose logs -f

# Solo el backend
docker-compose logs -f backend

# Archivo de log del backend
docker exec asir_backend tail -f /app/logs/fichaje.log
```

---

## Seguridad implementada

- ✅ Sin credenciales en el código fuente (todo en `.env`)
- ✅ Contraseñas almacenadas con hash bcrypt
- ✅ Autenticación JWT con expiración configurable
- ✅ Protección contra fuerza bruta (bloqueo tras N intentos fallidos)
- ✅ Control de acceso por roles (user / admin)
- ✅ Validación estricta de todos los inputs con Pydantic
- ✅ Registro de auditoría de accesos y acciones
- ✅ HTTPS mediante Nginx con TLS 1.2/1.3
- ✅ Cabeceras de seguridad HTTP (X-Frame-Options, HSTS, etc.)
- ✅ `.env` y certificados excluidos del repositorio

---

## Funcionalidades principales

### Empleado
- Fichar entrada / descanso / comida / salida con GPS
- Validación de geofencing (zona permitida de fichaje)
- Historial de fichajes con filtro por fechas y exportación CSV
- Informe diario y mensual de horas trabajadas
- Solicitar preavisos de ausencia o retraso
- Recibir documentos corporativos

### Administrador
- Monitor en tiempo real del estado de todos los empleados
- Alta, listado y desactivación de usuarios
- Generación automática de alertas de faltas
- Gestión de solicitudes de preavisos (aprobar/rechazar)
- Envío de documentos corporativos via FTPS
- Acceso a logs de auditoría

---

## Datos de prueba

Al arrancar con `SEED_DATA=true` (valor por defecto), el sistema crea automáticamente los siguientes usuarios con **30 días de historial** de fichajes realistas:

| Rol   | Email                        | Contraseña |
|-------|------------------------------|-----------|
| Admin | admin@asir.com               | 1234      |
| User  | juan.perez@asir.com          | 1234      |
| User  | maria.garcia@asir.com        | 1234      |
| User  | carlos.sanchez@asir.com      | 1234      |
| User  | laura.rodriguez@asir.com     | 1234      |

Los fichajes se generan con coordenadas reales de Jerez de la Frontera (±100 m de variación), incluyendo entradas, pausas, comidas, salidas, alertas de retraso y preavisos pendientes listos para revisar en el panel de administración.

Para ejecutar el seed manualmente en cualquier momento:
```bash
docker exec asir_backend python seed.py
```

Para desactivar el seed en producción, añadir al `.env`:
```
SEED_DATA=false
```

---

## Cumplimiento normativo

El sistema implementa el registro de jornada laboral requerido por el **Real Decreto-Ley 8/2019**, almacenando para cada empleado:
- Hora exacta de inicio y fin de jornada
- Identidad del trabajador
- Trazabilidad de todas las modificaciones
