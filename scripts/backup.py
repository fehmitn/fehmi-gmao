"""Sauvegarde à chaud de la base SQLite.

L'API de sauvegarde de SQLite (``connection.backup``) produit une copie
cohérente même si l'application écrit pendant l'opération. Un simple
« cp gmao.db sauvegarde.db » n'offre pas cette garantie en mode WAL : on
copierait un fichier possiblement incomplet.

Usage (dans le conteneur) :
    python scripts/backup.py                        # -> /data/backup/gmao-<date>.db
    python scripts/backup.py /data/snapshots/avant-migration.db

Récupérer la sauvegarde sur l'hôte (Docker Desktop / Linux) :
    docker cp gmao:/data/backup/gmao-20261022-101500.db .\\sauvegardes\\
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DATABASE_URL  # noqa: E402


def source_path(database_url: str) -> Path:
    """Extrait le chemin du fichier SQLite de l'URL SQLAlchemy.

    Trois formes sont possibles :
      * ``sqlite:////data/gmao.db``      -> chemin absolu POSIX (conteneur) ;
      * ``sqlite:///C:/données/gmao.db``  -> chemin absolu Windows ;
      * ``sqlite:///./gmao.db``           -> chemin relatif au dossier courant.
    """
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise SystemExit(
            f"Sauvegarde : URL non-SQLite non gérée ({database_url}). "
            "Utilisez pg_dump / mysqldump selon le moteur."
        )
    raw = database_url[len(prefix) :]
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return Path(raw)
    return Path(raw)


def backup(target: Path) -> Path:
    """Écrit une copie cohérente de la base dans ``target``."""
    origin = source_path(DATABASE_URL)
    if not origin.exists():
        raise SystemExit(f"Sauvegarde : base introuvable ({origin}).")

    target.parent.mkdir(parents=True, exist_ok=True)

    # Lecture seule sur la source : aucune modification pendant la copie.
    with closing(sqlite3.connect(origin.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)

    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Sauvegarde à chaud de la base GMAO.")
    parser.add_argument(
        "destination",
        nargs="?",
        help="Fichier .db de destination (défaut : /data/backup/gmao-<date>.db).",
    )
    args = parser.parse_args()

    if args.destination:
        target = Path(args.destination)
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = Path("/data/backup") / f"gmao-{stamp}.db"

    path = backup(target)
    size_kb = round(path.stat().st_size / 1024, 1)
    print(f"Sauvegarde écrite : {path} ({size_kb} Ko)")


if __name__ == "__main__":
    main()
