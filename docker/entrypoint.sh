#!/usr/bin/env sh
#
# Point d'entrée du conteneur GMAO.
#
#   1. migrations Alembic (crée ou met à niveau le schéma + données de réf.) ;
#   2. jeu de démonstration (optionnel, GMAO_SEED=true) ;
#   3. serveur uvicorn.
#
# Toute erreur de migration arrête le conteneur : mieux vaut un échec
# visible au démarrage qu'une application qui écrit dans un schéma obsolète.

set -eu

DATA_DIR="${GMAO_DATA_DIR:-/data}"
PORT="${PORT:-8000}"

echo "[gmao] dossier de données : ${DATA_DIR}"
mkdir -p "${DATA_DIR}"

echo "[gmao] migrations (alembic upgrade head)…"
alembic upgrade head

# La décision passe par app.config : une seule source de vérité pour
# l'activation du seed (GMAO_SEED=true).
if python -c "from app.config import SEED_ON_STARTUP; raise SystemExit(0 if SEED_ON_STARTUP else 1)"; then
    echo "[gmao] jeu de démonstration…"
    # Le script détecte un jeu déjà présent et ne fait rien : il est rejouable.
    python scripts/seed.py || echo "[gmao] seed non bloquant : ignoré"
fi

echo "[gmao] démarrage de l'API sur 0.0.0.0:${PORT}"
# Un seul worker : plusieurs processus ouvrent des connexions concurrentes
# sur le même fichier SQLite, ce qui multiplie les conflits d'écriture.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips '*'
