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

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
