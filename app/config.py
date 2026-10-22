"""Configuration de l'application, lisible depuis l'environnement ou le fichier .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

#: Racine du projet, utile pour les chemins par défaut.
PROJECT_ROOT = BASE_DIR

#: Dossier des données persistantes. En conteneur, c'est le point de montage
#: du volume Docker (``/data`` par défaut) : le fichier SQLite doit vivre
#: hors de la couche inscriptible du conteneur, sinon il disparaît à chaque
#: recréation de l'image.
DATA_DIR = Path(os.getenv("GMAO_DATA_DIR") or BASE_DIR)

#: URL de connexion SQLAlchemy. Par défaut : SQLite dans le dossier de données.
#: En conteneur : ``sqlite:////data/gmao.db`` (4 barres = chemin absolu).
DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{(DATA_DIR / 'gmao.db').as_posix()}"

#: Délai d'attente (ms) lorsqu'une connexion trouve la base verrouillée.
#: Évite l'erreur « database is locked » en cas d'accès concurrent.
SQLITE_BUSY_TIMEOUT_MS = int(os.getenv("SQLITE_BUSY_TIMEOUT_MS") or "5000")

#: Charger le jeu de démonstration au démarrage (conteneur uniquement).
SEED_ON_STARTUP = (os.getenv("GMAO_SEED") or "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

#: Dossier des templates Jinja2.
TEMPLATES_DIR = Path(__file__).resolve().parent / "web" / "templates"

#: Dossier des fichiers statiques.
STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"

#: Nom du cookie qui mémorise l'utilisateur courant (audit).
CURRENT_USER_COOKIE = "gmao_current_user"

#: Utilisateur système utilisé quand aucun cookie n'est posé.
SYSTEM_USERNAME = "systeme"

#: Profondeur maximale de l'arborescence des emplacements.
MAX_LOCATION_DEPTH = 5

#: Date de référence « aujourd'hui » injectable (tests de rétrodatation).
TODAY_OVERRIDE: str | None = os.getenv("GMAO_TODAY")
