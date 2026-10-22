# syntax=docker/dockerfile:1
#
# GMAO — image de production : un seul conteneur (serveur + données SQLite).
#
# Construire :  docker build -t gmao-app:0.2 .
# Lancer    :  docker run -p 8000:8000 -v gmao-data:/data gmao-app:0.2
#
# La base SQLite vit dans /data, monté en volume Docker : le conteneur
# contient bien « le serveur + les données », mais les données sont
# persistées sur le disque de la machine hôte, pas dans la couche
# inscriptible de l'image (qui disparaît à chaque recréation).

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Africa/Casablanca \
    GMAO_DATA_DIR=/data \
    DATABASE_URL=sqlite:////data/gmao.db

# tzdata : sans lui, le conteneur reste en UTC. Or le Maroc est en UTC+1 :
# entre 23h et minuit, « aujourd'hui » serait décalé d'un jour et le moteur
# de rétrodatation autoriserait (ou refuserait) à tort une saisie.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances d'abord : cette couche n'est invalidée que si requirements change.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Code applicatif (Alembic a besoin d alembic/ et de alembic.ini à la racine).
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# Utilisateur non-root et dossier de données.
# /data est créé et possédé ici : un volume Docker vide monté par-dessus en
# hérite de ce propriétaire, donc l'utilisateur non-root peut y écrire.
RUN groupadd --gid 10001 gmao \
    && useradd --uid 10001 --gid gmao --home-dir /app --shell /usr/sbin/nologin --no-create-home gmao \
    && mkdir -p /data \
    && chown -R gmao:gmao /data /app \
    && sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh

USER gmao

VOLUME ["/data"]
EXPOSE 8000

# La sonde interroge la base, pas seulement le processus HTTP.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
