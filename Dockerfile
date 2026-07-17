# ---------- Stage 1: build the React frontend ----------
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: backend runtime ----------
FROM python:3.12-slim AS backend
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# System libs: xmlsec stack is required by python3-saml (SAML module).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    xmlsec1 \
    pkg-config \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Built SPA goes where FastAPI serves it.
COPY --from=frontend /frontend/dist ./app/static

RUN chmod +x ./docker-entrypoint.sh

# TLS material is written here at boot (self-signed by default). The DB remains
# the source of truth; this dir is just what uvicorn's SSLContext reads.
ENV CERT_DIR=/app/certs
RUN mkdir -p /app/certs

# Two serving modes (see app/server.py, selected by TLS_ENABLED):
#   8000 = plain HTTP  -> TLS_ENABLED=false, infra terminates TLS (GKE model)
#   8443 = HTTPS        -> TLS_ENABLED=true  (default), app terminates TLS
# HTTP->HTTPS redirection is always the infrastructure's job, not the app's.
EXPOSE 8000 8443
ENTRYPOINT ["./docker-entrypoint.sh"]
