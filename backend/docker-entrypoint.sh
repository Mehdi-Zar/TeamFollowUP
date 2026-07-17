#!/bin/sh
set -e

echo "[entrypoint] Attente de la base de données..."
python - <<'PY'
import time, sys
import psycopg2
from app.config import settings

for attempt in range(60):
    try:
        conn = psycopg2.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
        )
        conn.close()
        print("[entrypoint] Base de données disponible.")
        sys.exit(0)
    except Exception as exc:
        print(f"[entrypoint] DB indisponible ({attempt + 1}/60): {exc}")
        time.sleep(2)
print("[entrypoint] La base de données n'est jamais devenue disponible.", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] Application des migrations Alembic..."
alembic upgrade head

echo "[entrypoint] Bootstrap (compte de secours) + seed de démonstration..."
python -m app.init_db

echo "[entrypoint] Démarrage de l'API..."
# server.py choisit le mode selon TLS_ENABLED :
#   - TLS_ENABLED=false : HTTP simple sur HTTP_PORT (8000) ; c'est l'infra
#     (Gateway API + ALB sur GKE) qui termine le TLS. Modèle recommandé.
#   - TLS_ENABLED=true (défaut) : l'app termine le TLS elle-même sur 8443
#     (certificat auto-signé par défaut, ou importé via l'admin).
# La redirection HTTP->HTTPS reste gérée par l'infra, jamais par l'app.
exec python -m app.server
