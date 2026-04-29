FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias primero para aprovechar la caché de capas Docker.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Crear directorio de logs con permisos adecuados.
RUN mkdir -p /app/logs

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
