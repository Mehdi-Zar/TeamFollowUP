# ---------- Stage 1: build the React frontend ----------
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
# Extra root authorities for a network that inspects HTTPS (see build-certs/README.md).
# Empty in CI and production: npm then trusts the public roots only, as before.
COPY build-certs/ /tmp/build-certs/
RUN if ls /tmp/build-certs/*.crt >/dev/null 2>&1; then         cat /tmp/build-certs/*.crt > /tmp/extra-ca.pem;         export NODE_EXTRA_CA_CERTS=/tmp/extra-ca.pem;     fi;     npm install
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
# Extra root authorities for a network that inspects HTTPS (see build-certs/README.md),
# added to the system store; pip is pointed at it. Empty in CI and production.
COPY build-certs/ /usr/local/share/ca-certificates/build-certs/
RUN update-ca-certificates
COPY backend/requirements.txt ./
RUN PIP_CERT=/etc/ssl/certs/ca-certificates.crt pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Built SPA goes where FastAPI serves it.
COPY --from=frontend /frontend/dist ./app/static

RUN chmod +x ./docker-entrypoint.sh

# Scratch dir for the outbound trust bundle (the public roots merged with the
# authorities imported in Administration). The DB stays the source of truth.
ENV CERT_DIR=/app/certs
RUN mkdir -p /app/certs
# Not root: an unprivileged account owns the app (a flaw in the app would
# otherwise act as root in the container).
RUN useradd --system --uid 10001 --home /app --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER 10001

# One port, plain HTTP: TLS is terminated by the infrastructure in front of the
# container, HTTP->HTTPS redirection included. See ADR 0013.
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
