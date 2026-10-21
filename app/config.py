"""Configuration de l'application, lisible depuis l'environnement ou le fichier .env."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

#: Racine du projet, utile pour les chemins par défaut.
PROJECT_ROOT = BASE_DIR

#: URL de connexion SQLAlchemy. Par défaut : SQLite dans le dossier du projet.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'gmao.db').as_posix()}")

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
