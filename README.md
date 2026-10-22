# GMAO — application pédagogique de gestion de maintenance assistée par ordinateur

Application web de gestion de maintenance (GMAO) construite comme **support
pédagogique**. Elle transpose le modèle de données de la documentation
**WinMaint** vers une architecture moderne (FastAPI + SQLAlchemy + SQLite +
Jinja2/HTMX) et met en scène sa fonctionnalité centrale : **la saisie
d'opérations datées dans le passé**, normalement interdite dans un GMAO
industriel.

---

## 1. Le parti pris pédagogique : la rétrodatation encadrée

Dans un GMAO de production, on refuse (ou on limite strictement) la saisie
d'une intervention datée dans le passé : une intervention saisie le 12 mars
pour le 10 mars fausse le calcul du MTBF, le taux de réalisation du
préventif et la charge des techniciens.

Cette application fait **l'inverse**, pour permettre un TP complet :

| Règle | Comportement |
|---|---|
| Date dans le **passé** | **Autorisée**, mais encadrée |
| **Motif de dérogation** | **Obligatoire** dès que la date est passée |
| **Retard de saisie** | Mesuré (en jours) et conservé avec l'opération |
| **Journalisation** | Action d'audit dédiée (`backdate`) : auteur, date, motif |
| Date dans le **futur** | **Toujours interdite**, même avec dérogation |
| Antériorité abusive | Refusée si la date précède l'origine admissible (mise en service, implantation en cours) |

Concrètement, chaque ligne d'implantation conserve une **empreinte de
rétrodatation** (`recorded_at`, `entry_delay_days`, `derogation_reason`) et le
tableau de bord affiche les dernières saisies rétroactives à justifier.

> Le moteur (`app/services/backdating.py`) est indépendant du métier : il
> servira tel quel au module « interventions » de l'itération 2.

---

## 2. Correspondance WinMaint → modèle de données

| WinMaint (doc de référence) | Entité GMAO | Table |
|---|---|---|
| **Clienti / sede** (usine, site) | Usine | `sites` |
| Arborescence **sedi / sede → Stable → Settore** | Emplacement (hiérarchique) | `locations` |
| Nature d'emplacement (bâtiment, atelier, zone, ligne) | Type d'emplacement | `location_types` |
| **Articoli installati** (articles installés) | Équipement | `equipments` |
| **Modelli di apparecchiature** (modèles pré-remplis) | Type / famille d'équipement | `equipment_types` |
| Implantation d'un article dans une sede | Implantation (avec historique) | `equipment_locations` |
| **Motore di ricerca** (moteur de recherche) | Filtres de la liste des équipements | `equipments` + `/equipments/table` |
| **Gestione utenti** (utilisateurs, droits) | Utilisateur + rôle | `users` |
| — | Piste d'audit / dérogations | `audit_logs` |
| **Chiamate / Interventi** (interventions) | *Itération 2* | *(prévu)* |

Le modèle distingue deux notions que WinMaint porte dans une seule table :
un équipement n'a pas d'emplacement « en dur », il est **implanté** dans un
emplacement via une période (`effective_from` / `effective_to`). C'est ce qui
permet de répondre à la question « **où était cette machine le 12/03/2024 ?** »
— question indispensable pour rattacher correctement une intervention saisie
a posteriori.

---

## 3. Démarrage

```bash
cd gmao-app
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt   # Windows
# pip install -r requirements-dev.txt                # Linux / macOS

.venv\Scripts\alembic.exe upgrade head              # crée le schéma
.venv\Scripts\python.exe scripts\seed.py            # jeu de démonstration
.venv\Scripts\uvicorn.exe app.main:app --reload
```

Puis :

| URL | Contenu |
|---|---|
| http://127.0.0.1:8000/ | Interface web (tableau de bord) |
| http://127.0.0.1:8000/docs | Documentation interactive de l'API |
| http://127.0.0.1:8000/api/stats/dashboard | Exemple de réponse JSON |

Variables d'environnement (fichier `.env`, voir `.env.example`) :

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | URL SQLAlchemy (SQLite par défaut dans le projet) |
| `GMAO_TODAY` | Date « du jour » figée — pratique pour tester la rétrodatation |

---

## 4. Le TP, pas à pas

### Étape 1 — Poser le référentiel

1. `Usines` → créer **USN-01** (Casablanca) et **USN-02** (Tanger).
2. `Emplacements` → dans USN-01, créer l'arborescence :
   `BAT-01` (bâtiment) → `ATL-01` (atelier) → `ZON-01` (zone des pompes).
   L'onglet de droite affiche la fiche de l'emplacement sélectionné
   (chargement HTMX, sans rechargement de page).
3. `Types d'équipements` → créer **PMP-CF** « Pompe centrifuge » (catégorie
   *Pompes*, constructeur *Grundfos*, modèle *CR 15-6*, criticité *B*).
   Ce type sert de **modèle** : il pré-remplit les champs de l'équipement.

### Étape 2 — Saisir un équipement

1. `Équipements` → `+ Nouvel équipement`.
2. Renseigner code, désignation, type, usine et emplacement.
3. Laisser la **date d'effet** à aujourd'hui : la saisie est « en temps réel ».
4. Enregistrer : l'équipement est créé **et** son implantation est ouverte.

### Étape 3 — Tester la rétrodatation (cœur du TP)

1. Reprendre la fiche d'un équipement et aller jusqu'à « Déplacer l'équipement ».
2. Choisir un nouvel emplacement et une **date d'effet passée**.
3. Le bloc jaune « Motif de la saisie rétroactive » apparaît :
   **sans motif, l'enregistrement est refusé**.
4. Renseigner le motif → l'enregistrement passe, et :
   - l'historique affiche le **retard en jours** ;
   - le **journal d'audit** (`/audit`) contient une entrée `backdate` ;
   - le **tableau de bord** liste la saisie rétroactive à justifier.

5. Essayer une date **future** : le refus est explicite, même avec un motif.

### Étape 4 — Jouer avec l'historique

1. Sur la fiche d'un équipement, l'historique d'implantation montre les
   périodes (`Du` / `Au`) et les emplacements successifs.
2. Un déplacement **saisi en retard** repositionne le passé : la période
   précédente se clôture à la veille de la date d'effet.

### Étape 4 bis — Reprendre un équipement hérité (cas réel)

1. Le tableau de bord affiche **1 équipement « sans emplacement »** : c'est
   `EQ-001`, l'équipement repris de la version 0.1 (son emplacement n'était
   qu'un texte libre, il n'a donc pas pu être implanté automatiquement).
2. Ouvrir sa fiche : le formulaire s'intitule **« Implanter l'équipement »**
   au lieu de « Déplacer l'équipement ».
3. Choisir l'emplacement `NA-001 / Non affecté` et une date d'effet **passée**
   (la machine était déjà sur site) → le motif de dérogation est exigé, puis
   l'implantation est enregistrée avec son retard (60 jours) et son motif.
4. Le compteur « Sans emplacement » du tableau de bord repasse à 0 et
   `EQ-001` apparaît dans l'historique du site `USINE-HIST`.

### Étape 5 — Filtrer

La liste des équipements combine : recherche texte, usine, emplacement
(**avec ou sans** les sous-emplacements), type, statut et criticité. Le
moteur de recherche WinMaint (*Motore di ricerca*) est ici traduit en
requêtes HTTP documentées sur `/api/equipments`.

---

## 5. API REST

| Méthode | Route | Description |
|---|---|---|
| `GET` | `/api/sites` | Liste des usines |
| `POST` | `/api/sites` | Créer une usine |
| `GET` | `/api/location-types` | Types d'emplacement |
| `GET` | `/api/sites/{id}/locations` | Emplacements d'une usine |
| `POST` | `/api/locations` | Créer un emplacement |
| `GET` | `/api/equipment-types` | Types d'équipements |
| `GET` | `/api/equipments` | Liste filtrable (`search`, `site_id`, `location_id`, `include_descendants`, `status`, `criticality`, `category`) |
| `POST` | `/api/equipments` | Créer un équipement (+ son implantation) |
| `GET` | `/api/equipments/{id}/placements` | Historique d'implantation |
| `POST` | `/api/equipments/{id}/placements` | Déplacer (date d'effet + dérogation) — ou implanter si l'équipement n'en a pas encore |
| `GET` | `/api/audit` | Journal d'audit |
| `GET` | `/api/stats/dashboard` | Indicateurs du tableau de bord |

L'utilisateur courant est identifié par le cookie `gmao_current_user`
(interface web) ou l'en-tête `X-GMAO-User` (API). L'itération 1 utilise une
simple sélection d'utilisateur, sans mot de passe : l'objectif est
pédagogique (voir *qui* saisit *quoi*), pas la sécurité.

---

## 6. Structure du projet

```
gmao-app/
├── alembic/                  migrations (source de vérité : les modèles)
│   └── versions/0001_baseline.py
├── app/
│   ├── api/                  routes REST JSON (/api)
│   ├── models/               modèles SQLAlchemy (8 tables)
│   ├── repositories/         accès aux données (CTE récursive, pagination)
│   ├── schemas/              contrats Pydantic (entrées / sorties)
│   ├── services/             règles métier (dont backdating.py)
│   ├── web/                  interface Jinja2 + HTMX
│   │   ├── templates/        pages et partials
│   │   └── static/           css, js, Bootstrap & HTMX vendorisés (hors ligne)
│   ├── config.py             configuration (DATABASE_URL, GMAO_TODAY…)
│   ├── database.py            moteur SQLAlchemy + PRAGMA SQLite
│   ├── errors.py             exceptions du domaine
│   └── main.py               point d'entrée (API + web + statique)
├── docker/
│   └── entrypoint.sh         migrations + seed optionnel + uvicorn
├── scripts/seed.py           jeu de démonstration
├── scripts/backup.py         sauvegarde à chaud de la base SQLite
├── tests/                    58 tests pytest
├── Dockerfile                image de production (un seul conteneur)
├── docker-compose.yml        service unique + volume de données
└── requirements.txt          dépendances de production
```

**Choix techniques notables**

- **Bootstrap 5 et HTMX sont vendorisés** dans `app/web/static/vendor/` :
  l'application fonctionne sans connexion internet.
- **`PRAGMA foreign_keys=ON`** est activé à chaque connexion SQLite : les
  clés étrangères sont réellement appliquées.
- **Mode WAL + `busy_timeout`** : les lectures ne bloquent plus l'écriture et
  les accès concurrents attendent au lieu d'échouer sur « database is locked ».
- **Index unique partiel** sur `equipment_locations(equipment_id)` quand
  `effective_to IS NULL` : une seule implantation ouverte par équipement,
  garantie par la base et non seulement par le code.
- **CTE récursive** pour calculer les sous-arbres d'emplacements (filtres
  « cet atelier et ses sous-emplacements »).

---

## 7. Tests

```bash
.venv\Scripts\python.exe -m pytest
```

La base de test est un fichier SQLite temporaire et la date du jour est
figée (`GMAO_TODAY=2026-06-15`) : les tests sont déterministes.

> Les tests de développement nécessitent `requirements-dev.txt`
> (`pytest`, `httpx`) ; l'image de production n'embarque que
> `requirements.txt`.

| Fichier | Couverture |
|---|---|
| `tests/test_backdating.py` | motif obligatoire, futur interdit, antériorité, empreinte, audit |
| `tests/test_placements.py` | périodes, cohérence des dates, fermeture, déplacement entre usines, implantation d'un équipement sans emplacement |
| `tests/test_equipment.py` | unicité du code, pré-remplissage depuis le type, filtres |
| `tests/test_locations.py` | arborescence, unicité par usine, cycles, suppression protégée |
| `tests/test_api.py` | API REST et pages web |

---

## 8. Suite proposée (itération 2)

Le module **interventions** (OT / ordres de travail) doit réutiliser
`BackdatingPolicy` tel quel : une intervention saisie a posteriori
sera datée, justifiée, et rattachée à **l'emplacement de l'équipement à la
date de l'intervention** — ce que permet déjà la table
`equipment_locations`.

Autres pistes : gestion des stocks et pièces de rechange, plans de
maintenance préventive, calcul du MTBF/MTTR, authentification réelle et
rôles (le champ `users.role` est déjà en place).

---

## 9. Déploiement Docker (un seul conteneur)

L'application est déployable telle quelle : **un conteneur unique** qui
contient le serveur (FastAPI + uvicorn) **et** la base SQLite. Aucune base
de données externe, aucun service annexe.

```
┌─ conteneur "gmao" (python:3.12-slim, utilisateur non-root) ───────┐
│  /app     code applicatif (lecture seule)                         │
│  /data ◄── volume Docker "gmao-data"  (gmao.db, -wal, -shm)       │
└───────────────────────────────────────────────────────────────────┘
```

> **Pourquoi un volume ?** La couche inscriptible d'un conteneur est
> éphémère : `docker compose down`, ou la reconstruction de l'image,
> effacerait le fichier `gmao.db`. Le volume Docker le persiste sur le
> disque de la machine hôte. Le conteneur contient bien « le serveur et
> les données », mais les données survivent au conteneur.

### Démarrage

```bash
docker compose up -d --build     # construire et démarrer
docker compose logs -f           # suivre les logs
docker compose ps                # état + santé du conteneur
```

| URL | Contenu |
|---|---|
| http://localhost:8000/ | Interface web (tableau de bord) |
| http://localhost:8000/docs | Documentation interactive de l'API |
| http://localhost:8000/health | Sonde de santé (ping de la base) |

### Séquence de démarrage

`docker/entrypoint.sh` s'exécute avant uvicorn :

1. `alembic upgrade head` — crée le schéma et les données de référence
   (types d'emplacements, utilisateurs). Une erreur de migration **arrête**
   le conteneur : mieux vaut un échec visible qu'un schéma obsolète.
2. `python scripts/seed.py` — uniquement si `GMAO_SEED=true`. Le script
   détecte un jeu déjà présent et ne fait rien : il est rejouable sans
   risque.
3. `exec uvicorn app.main:app --workers 1` — **un seul worker**, car
   plusieurs processus ouvrent des connexions concurrentes sur le même
   fichier SQLite.

### Configuration

Les variables sont définies dans `docker-compose.yml` :

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | `sqlite:////data/gmao.db` (4 barres = chemin absolu) |
| `GMAO_DATA_DIR` | `/data`, point de montage du volume |
| `GMAO_SEED` | `true` pour charger le jeu de démonstration au démarrage |
| `SQLITE_BUSY_TIMEOUT_MS` | attente sur verrou SQLite (5000 par défaut) |
| `TZ` | `Africa/Casablanca` — sans `tzdata` dans l'image, le conteneur resterait en UTC et « aujourd'hui » serait décalé d'un jour |

Ne jamais définir `GMAO_TODAY` en production : la date du jour doit être
réelle.

### Sauvegarde

La base vit dans la machine virtuelle de Docker Desktop : pour l'examiner
ou la sauvegarder, on passe par `docker cp` ou le script dédié.

```bash
# Sauvegarde à chaud (cohérente même pendant les écritures)
docker compose exec gmao python scripts/backup.py
docker cp gmao:/data/backup/gmao-20261022-101500.db .\sauvegardes\

# Copie brute à froid (conteneur arrêté)
docker compose stop
docker cp gmao:/data/gmao.db .\sauvegardes\gmao.db
docker compose start
```

`scripts/backup.py` utilise l'API de sauvegarde de SQLite
(`connection.backup`) : un simple `cp` du fichier `.db` ne garantit rien en
mode WAL, où les écritures récentes vivent dans le fichier `-wal`.

### Cycle de vie du volume

```bash
docker compose down      # arrête le conteneur, conserve le volume
docker compose down -v   # supprime AUSSI la base : à manier avec prudence
```

---

## 10. Historique

- **v0.1** — prototype minimal : une table `equipments` avec l'emplacement
  en texte libre.
- **v0.2** — refonte complète (ce document) : modèle WinMaint transposé,
  arborescence d'emplacements multi-usines, historique d'implantation,
  moteur de rétrodatation, API REST + interface web, migrations Alembic.
- **v0.2.1** — déploiement conteneurisé : image Docker, service unique avec
  volume de données SQLite, migrations au démarrage, sauvegarde à chaud.
