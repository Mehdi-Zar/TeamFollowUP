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

# Scratch dir for the outbound trust bundle (the public roots merged with the
# authorities imported in Administration). The DB stays the source of truth.
ENV CERT_DIR=/app/certs
RUN mkdir -p /app/certs

# One port, plain HTTP: TLS is terminated by the infrastructure in front of the
# container, HTTP->HTTPS redirection included. See ADR 0013.
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
