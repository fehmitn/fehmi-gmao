from collections.abc import Generator
import sys

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL, SQLITE_BUSY_TIMEOUT_MS

_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


if _is_sqlite:

    @event.listens_for(Engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record) -> None:
        """Configure chaque connexion SQLite.

        * ``foreign_keys=ON`` : sans ce PRAGMA, les contraintes d'intégrité
          (site -> emplacement -> equipement) ne seraient que des suggestions
          applicatives, SQLite les ignore par défaut.
        * ``busy_timeout`` : en cas d'accès concurrent, la connexion attend
          au lieu de lever « database is locked ».
        * ``journal_mode=WAL`` : les lectures ne bloquent plus l'écriture.
          Le mode est persistant dans le fichier de base.
        * ``synchronous=NORMAL`` : compromis sûr en WAL (durable au niveau du
          système de fichiers, pas de l'unité de stockage).
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except OperationalError:
            # Système de fichiers sans verrous POSIX fiables (bind mount
            # réseau, NTFS via Docker Desktop) : on reste en mode DELETE,
            # plus lent mais correct.
            pass
        finally:
            cursor.close()


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Crée le schéma si nécessaire et aligne la version Alembic.

    En production, le schéma est piloté par Alembic (``alembic upgrade head``
    au démarrage du conteneur) : la table ``alembic_version`` existe alors et
    l'on ne touche à rien. Sans cette garde, ``create_all`` recréerait un
    schéma « à côté » de celui des migrations, sans table de version, et la
    migration suivante échouerait sur des tables déjà existantes.

    Si l'application est démarrée sans migration (uvicorn lancé à la main sur
    une base vide), le schéma est créé depuis les modèles *et* la version
    Alembic est alignée : la migration suivante saura qu'il n'y a rien à
    faire au lieu d'échouer sur « table already exists ».
    """
    from app import models  # noqa: F401 - enregistre les modèles sur Base

    if "alembic_version" in inspect(engine).get_table_names():
        return

    Base.metadata.create_all(bind=engine)
    _stamp_alembic_head()


def _stamp_alembic_head() -> None:
    """Marque la base comme à jour vis-à-vis d'Alembic, sans exécuter les scripts."""
    from alembic import command
    from alembic.config import Config

    from app.config import BASE_DIR

    if BASE_DIR.as_posix() not in sys.path:
        sys.path.insert(0, BASE_DIR.as_posix())

    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "alembic"))
    config.set_main_option("prepend_sys_path", BASE_DIR.as_posix())
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.stamp(config, "head")
