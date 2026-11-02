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
| **Piani di manutenzione periodica** | Contrainte périodique d'une famille | `periodic_maintenances` |
| **Fornitori / terzisti** | Fournisseur de maintenance | `maintenance_suppliers` |
| **Chiamate / Interventi** (interventions) | Réalisation d'OT rattachée à une règle | `maintenance_executions` |
| **Ricambi** (pièces de rechange) | Catalogue des pièces + mouvements de stock | `spare_parts`, `stock_movements` |
| **Attrezzature / strumenti di misura** | Équipement de maintenance non consommé | `maintenance_tools` |
| **Tarature / verifiche periodiche** | Registre des étalonnages | `tool_calibrations` |
| **Prestito attrezzature** | Prêt / utilisation lié à un OT | `tool_usages` |

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
| http://127.0.0.1:8000/ | Interface web (tableau de bord, après connexion) |
| http://127.0.0.1:8000/login | Connexion |
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

## 5. Maintenance périodique portée par les familles

Le module transpose les **plans de maintenance préventive** : les contraintes
sont définies **une seule fois sur la famille d'équipements**
(`equipment_types`), puis héritées automatiquement par tous ses équipements.
On évite ainsi de ressaisir les mêmes règles machine par machine.

| Notion | Portée | Table |
|---|---|---|
| Fournisseur de maintenance | Référentiel global | `maintenance_suppliers` |
| Contrainte périodique | Famille d'équipements | `periodic_maintenances` |
| Réalisation d'OT | Équipement + contrainte | `maintenance_executions` |

**Une contrainte** combine :

- une opération (`code`, libellé, description) et un type de maintenance
  (préventive systématique, conditionnelle, réglementaire, inspection) ;
- une **périodicité** : un nombre et une unité (jours, semaines, mois, années,
  ou **heures de fonctionnement**) ;
- un **ancrage** : mise en service de l'équipement (défaut), première
  implantation, ou date fixe. Il est toujours forcé à la mise en service pour
  une périodicité en heures ;
- un fournisseur facultatif, une tolérance en jours et une durée estimée.

**Calcul des échéances.** L'échéancier est une **projection théorique** : aucune
date n'est stockée par équipement. Les occurrences sont calculées depuis la
date d'ancrage, sans enchaîner les ajouts, afin d'éviter la dérive de fin de
mois (31 janvier + 2 mois = 31 mars). Une tolérance permet de classer une
échéance tout juste dépassée en « dans la tolérance » plutôt qu'en retard.

**Réalisations d'OT.** La saisie d'une réalisation est **append-only** : elle
fige l'échéance théorique de référence et l'écart signé en jours (négatif =
avance). Le retard est toujours mesuré **par rapport au référentiel**, jamais
depuis la dernière réalisation. Une date future est refusée. L'échéancier
considère l'occurrence précédente comme couverte si la dernière réalisation
porte sur une échéance de référence au moins égale.

**Périodicités en heures de fonctionnement.** Chaque équipement porte un
**compteur horaire courant** (`operating_hours`) et un **relevé initial à la
mise en service** (`initial_operating_hours`). L'application ne peut pas
prévoir à l'avance quand un seuil sera franchi : elle ne calcule donc pas de
date d'échéance et laisse la ligne **ouverte** dans l'échéancier.

- Premier cycle : les seuils déjà franchis depuis le relevé initial sont
  ignorés ; le prochain multiple de l'intervalle est affiché.
- Contrôle à planifier : dès qu'il reste **10 heures ou moins** avant le
  seuil, la ligne passe en `heures à planifier`.
- Seuil atteint ou dépassé : après une réalisation, le cycle suivant repart du
  relevé saisi ; tant que le compteur n'est pas redescendu, la ligne reste en
  `seuil d'heures dépassé`.
- Une réalisation en heures fige le **relevé du compteur** (pas d'échéance ni
  d'écart en jours) et met à jour le compteur de l'équipement s'il progresse.
- Aucun ordre de travail n'est généré automatiquement : la ligne ouverte joue
  le rôle de rappel.

**Cycle de démonstration** :

1. créer un fournisseur dans `Fournisseurs de maintenance` ;
2. ouvrir une famille dans `Types d'équipements` et ajouter ses contraintes,
   y compris une périodicité en heures ;
3. renseigner le compteur horaire sur la fiche d'un équipement de cette
   famille ;
4. consulter `Échéancier` (filtres usine / famille / fournisseur / horizon) :
   les lignes en heures affichent le seuil, le compteur et les heures restantes ;
5. saisir une réalisation depuis l'échéancier ou la fiche équipement ;
6. vérifier le retard ou le relevé horaire dans l'historique et le journal
   d'audit (`execute`).

> Périmètre volontairement limité à la **configuration + l'échéancier** : la
> génération automatique d'ordres de travail reste une évolution ultérieure.

---

## 6. Pièces de rechange et équipements de maintenance

### 6.1 Pièces de rechange

Le module **Inventaire → Pièces de rechange** tient un catalogue de pièces
consommables et leur stock. Chaque pièce porte un code, une désignation, une
catégorie, un fournisseur, une usine, un emplacement de stockage, une unité,
un seuil minimum, un stock maximum facultatif et un coût unitaire.

**Le stock n'est jamais modifié directement.** Il évolue uniquement par des
**mouvements append-only** :

| Mouvement | Effet |
|---|---|
| `Entrée` | Ajoute la quantité reçue |
| `Sortie` | Retire la quantité consommée (refusée si le stock est insuffisant) |
| `Inventaire` | Aligne le stock sur la quantité réellement comptée |

Un mouvement peut être rattaché à un **ordre de travail** et à un document
(bon de commande, bon de sortie…), avec un motif. Une date future est refusée.
À la création d'une pièce, un stock initial positif génère automatiquement un
mouvement d'entrée « Stock initial ». Une erreur de saisie se corrige par un
mouvement inverse : l'historique n'est ni modifiable ni supprimable.

Les pièces actives dont le stock atteint le seuil minimum sont signalées dans
le tableau de bord. Une pièce qui possède un historique ne peut pas être
supprimée : on la désactive pour la retirer des alertes de réapprovisionnement.

**Pièces compatibles.** La fiche d'une pièce permet de déclarer qu'elle peut
**remplacer** une autre pièce (même unité obligatoire, relation enregistrée
dans `spare_part_interchanges`). La relation est volontairement **orientée** :
« A remplace B » n'implique pas « B remplace A ». Les prix des deux pièces sont
affichés côte à côte, avec un badge « moins chère » ou « plus chère » ; une
pièce plus chère reste autorisée, l'avertissement est purement indicatif.

Au moment de consommer une pièce demandée, le technicien voit la pièce
d'origine puis, en dessous, les pièces compatibles en stock, chacune avec son
prix. Il peut ainsi choisir délibérément une pièce moins chère même si le stock
de la pièce d'origine suffit. La sortie de stock est alors enregistrée sur la
pièce réellement consommée, et `intervention_parts.used_spare_part_id` conserve
la traçabilité de la substitution.

### 6.2 Équipements de maintenance

Le module **Inventaire → Équipements de maintenance** couvre les outils et
moyens de contrôle **non consommés** (pied à coulisse, micromètre, manomètre,
clé dynamométrique…). Chaque équipement possède sa propre **fiche
d'utilisation**, qui rassemble :

- son identité : code, désignation, catégorie, fabricant, modèle, numéro de
  série, usine et emplacement de stockage ;
- sa **contrainte légale d'étalonnage** : périodicité, dernier étalonnage,
  prochaine échéance, organisme, référence normative ;
- le **registre des étalonnages** (append-only) avec certificat, résultat,
  coût et observations ;
- l'**historique des prêts / utilisations**, rattaché à un ordre de travail et
  à un utilisateur, avec date de début, date de restitution et observations.

**Règles de disponibilité.** Un outil ne peut être emprunté que s'il est actif,
disponible, ni en maintenance ni hors service, et si son étalonnage est valide.
Le prêt est bloqué lorsqu'un étalonnage obligatoire est **manquant** ou **en
retard**. La restitution remet automatiquement l'outil en disponibilité. Un
étalonnage **non conforme** place l'outil hors service.

**Étalonnage calendaire uniquement.** Les unités autorisées sont les jours,
semaines, mois et années : un étalonnage ne peut pas être déclenché par des
heures de fonctionnement. La prochaine échéance est calculée automatiquement à
partir de la date d'étalonnage et de la périodicité, sauf si une date explicite
est fournie. Une alerte apparaît **30 jours** avant l'échéance.

Comme pour les pièces, un équipement qui possède un historique d'étalonnage ou
d'utilisation ne peut pas être supprimé : on le désactive ou on le passe en
« Réformé ». Le tableau de bord affiche les étalonnages en retard, à prévoir
sous 30 jours et jamais réalisés.

### 6.3 Migration

La migration `0005_inventory_tools` crée les tables `spare_parts`,
`stock_movements`, `maintenance_tools`, `tool_calibrations` et `tool_usages`,
avec leurs index et contraintes de clés étrangères. Elle ajoute également
l'index manquant `ix_work_orders_created_by_id` déjà déclaré dans le modèle.

La migration `0009_spare_part_interchanges` crée la table
`spare_part_interchanges` (contrainte d'unicité sur le couple
`part_id`/`replaces_id`) et ajoute `intervention_parts.used_spare_part_id`
pour mémoriser la pièce réellement consommée.

---

## 7. Maintenance corrective

Le module **Interventions** traite les pannes et demandes de dépannage, par
opposition aux OT préventifs générés depuis l'échéancier. Une intervention
corrective réutilise la numérotation des OT (`OT-<année>-<séquence>`) mais reste
identifiée par `work_orders.is_corrective = true` : elle n'apparaît donc pas
dans la page **Ordres de travail** et se pilote depuis sa propre fiche.

### 7.1 Circuit de traitement

| Étape | Acteur | Règle |
|---|---|---|
| Création de la demande | Tout utilisateur connecté | Équipement actif, symptôme obligatoire, priorité et date souhaitée facultatives |
| Affectation | `responsable` ou `admin` | Uniquement vers un `technicien`, un `responsable` ou un `admin` actif ; impossible une fois l'intervention démarrée |
| Démarrage | Technicien affecté ou manager | Enregistre l'heure précise de début et passe l'OT en `in_progress` |
| Consommation des pièces | Technicien affecté ou manager | Uniquement pendant l'intervention en cours |
| Clôture | Technicien affecté ou manager | Compte rendu obligatoire, heure de fin ≥ heure de début, durée calculée |
| Annulation | Demandeur ou manager | Impossible si une pièce a déjà été consommée |

Le cycle de statut est `open` → `assigned` → `in_progress` → `done`, avec
`cancelled` comme sortie alternative. Les services historiques `take`,
`assign` et `update_status` des OT préventifs refusent explicitement une
intervention corrective : chaque nature garde son propre workflow.

### 7.2 Pièces détachées

Une pièce suit deux temps :

1. **Demande** (`requested`) : le technicien indique la pièce et la quantité
   souhaitée. Aucun stock n'est encore mouvementé.
2. **Utilisation** (`used`) : la quantité réellement consommée est enregistrée.
   Une **sortie de stock append-only** est alors créée et rattachée à l'OT,
   avec contrôle du stock disponible.

Lors de l'utilisation, le formulaire présente la pièce demandée puis les pièces
compatibles, avec leur stock et leur prix. Choisir une pièce compatible
enregistre la sortie sur cette pièce (contrôle de compatibilité, d'activité et
de stock) et renseigne `used_spare_part_id` ; la note du mouvement rappelle la
pièce initialement demandée. Si le prix de la pièce choisie est supérieur, un
badge « plus chère » le signale sans bloquer l'opération.

Une demande encore en attente peut être annulée (`cancelled`). Une pièce déjà
utilisée reste définitivement tracée dans l'historique du stock : l'annulation
de l'intervention est alors refusée.

### 7.3 Migration

La migration `0006_corrective_maintenance` ajoute les colonnes
`is_corrective`, `intervention_started_at`, `intervention_ended_at` et
`work_done` à `work_orders`, puis crée la table `intervention_parts` avec ses
index et contraintes de clés étrangères.

La migration `0007_work_order_timestamps` rétablit la valeur par défaut
`CURRENT_TIMESTAMP` sur `work_orders.created_at` et `work_orders.updated_at`
(oubliée par la migration `0004`), afin que la création d'un OT fonctionne sur
une base réellement migrée et non seulement sur un schéma issu de
`create_all`.

### 7.4 Analyse de maintenance

La page **Analyse** (`/analytics`) exploite les horodatages et les mouvements
de stock déjà enregistrés pour produire des indicateurs de fiabilité et de
coût sur une fenêtre glissante de 30, 90 ou 365 jours :

| Indicateur | Formule retenue |
|---|---|
| **MTTR** | temps d'arrêt total ÷ nombre d'interventions correctives **terminées** |
| **MTBF** | (durée de la fenêtre − temps d'arrêt) ÷ nombre d'interventions terminées |
| **Disponibilité** | 1 − temps d'arrêt ÷ (durée de la fenêtre × nombre d'équipements actifs), bornée entre 0 et 1 |
| **Coût pièces** | somme des sorties de stock rattachées à un OT × coût unitaire figé au moment du mouvement |
| **Panne récurrente** | au moins 3 interventions correctives terminées sur les 12 derniers mois |

Le coût d'une pièce est **figé au moment de la sortie de stock**
(`stock_movements.unit_cost`) : une revalorisation ultérieure du catalogue ne
réécrit pas l'historique. Les mouvements antérieurs à la migration `0008` sont
initialisés avec le prix courant de leur pièce, puis le calcul applique ce
repli si le coût est absent.

La page propose un filtre par usine, un tri (disponibilité, MTTR, MTBF, nombre
de pannes, coût) et deux tableaux de synthèse : un classement des équipements
(les plus mauvais en tête) et le détail des coûts par ordre de travail. Les
pannes récurrentes sont signalées par un badge sur la fiche de l'équipement.

### 7.5 Alertes du tableau de bord

Le tableau de bord affiche un bloc **Alertes d'exploitation** qui remonte :

- les **demandes correctives non affectées** depuis au moins 3 jours ;
- les **OT préventifs en retard** (échéance dépassée, OT ni terminé ni annulé).

Les mêmes alertes sont exposées par l'API (`/api/analytics/alerts`) avec un
seuil et une limite paramétrables. La page **Ordres de travail** ne liste plus
que les OT préventifs (les interventions correctives gardent leur page dédiée)
et propose un filtre « En retard uniquement ».

### 7.6 Migration

La migration `0008_movement_costs` ajoute `stock_movements.unit_cost`, puis
initialise les mouvements existants avec le coût unitaire courant de leur
pièce. Les mouvements suivants capturent la valeur au moment de la saisie.

---

## 8. API REST

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
| `GET` | `/api/maintenance-suppliers` | Fournisseurs de maintenance (`active_only`) |
| `POST` | `/api/maintenance-suppliers` | Créer un fournisseur |
| `GET` | `/api/maintenance-suppliers/{id}` | Détail d'un fournisseur |
| `PUT` | `/api/maintenance-suppliers/{id}` | Modifier un fournisseur |
| `DELETE` | `/api/maintenance-suppliers/{id}` | Supprimer (refusé s'il est utilisé) |
| `GET` | `/api/equipment-types/{id}/periodic-maintenances` | Contraintes d'une famille |
| `POST` | `/api/equipment-types/{id}/periodic-maintenances` | Ajouter une contrainte |
| `GET` | `/api/periodic-maintenances/{id}` | Détail d'une contrainte |
| `PUT` | `/api/periodic-maintenances/{id}` | Modifier une contrainte |
| `DELETE` | `/api/periodic-maintenances/{id}` | Supprimer (refusé si des réalisations existent) |
| `GET` | `/api/equipments/{id}/maintenance-executions` | Réalisations d'un équipement |
| `POST` | `/api/equipments/{id}/maintenance-executions` | Saisir une réalisation (date future refusée ; `operating_hours` requis si la règle est en heures) |
| `GET` | `/api/maintenance-schedule` | Échéancier (`site_id`, `equipment_type_id`, `supplier_id`, `horizon_days`, `search`) |
| `GET` | `/api/spare-parts` | Catalogue filtrable (`search`, `category`, `low_stock_only`, `active_only`) |
| `GET` | `/api/spare-parts/summary` | Indicateurs de stock (seuils, ruptures, valeur) |
| `POST` | `/api/spare-parts` | Créer une pièce (+ mouvement « Stock initial ») |
| `GET` | `/api/spare-parts/{id}` | Détail d'une pièce |
| `PUT` | `/api/spare-parts/{id}` | Modifier la fiche (hors stock) |
| `DELETE` | `/api/spare-parts/{id}` | Supprimer (refusé si des mouvements existent) |
| `GET` | `/api/spare-parts/{id}/movements` | Historique des mouvements |
| `POST` | `/api/spare-parts/{id}/movements` | Enregistrer une entrée, une sortie ou un inventaire |
| `GET` | `/api/spare-parts/{id}/interchanges` | Compatibilités entrantes et sortantes de la pièce |
| `POST` | `/api/spare-parts/{id}/interchanges` | Déclarer que cette pièce remplace une autre |
| `DELETE` | `/api/spare-parts/{id}/interchanges/{interchange_id}` | Retirer une compatibilité |
| `GET` | `/api/spare-parts/{id}/replacement-candidates` | Pièces actives pouvant remplacer celle-ci |
| `GET` | `/api/maintenance-tools` | Fiches filtrables (`search`, `category`, `status_filter`, `calibration_status`, `active_only`) |
| `GET` | `/api/maintenance-tools/summary` | Indicateurs d'étalonnage et de disponibilité |
| `POST` | `/api/maintenance-tools` | Créer une fiche d'utilisation |
| `GET` | `/api/maintenance-tools/{id}` | Détail d'un équipement de maintenance |
| `PUT` | `/api/maintenance-tools/{id}` | Modifier la fiche |
| `PUT` | `/api/maintenance-tools/{id}/status` | Changer la disponibilité |
| `DELETE` | `/api/maintenance-tools/{id}` | Supprimer (refusé si un historique existe) |
| `GET` | `/api/maintenance-tools/{id}/calibrations` | Registre des étalonnages |
| `POST` | `/api/maintenance-tools/{id}/calibrations` | Enregistrer un étalonnage |
| `GET` | `/api/maintenance-tools/{id}/usages` | Historique des prêts / utilisations |
| `POST` | `/api/maintenance-tools/{id}/usages` | Démarrer une utilisation (bloquée si étalonnage invalide) |
| `POST` | `/api/maintenance-tools/{id}/usages/{usage_id}/return` | Restituer l'outil |
| `GET` | `/api/interventions` | Demandes correctives filtrables (`status_filter`, `assigned_to_id`, `search`, `open_only`) |
| `POST` | `/api/interventions` | Créer une demande d'intervention (`X-GMAO-User` requis) |
| `GET` | `/api/interventions/{id}` | Détail d'une intervention avec ses pièces |
| `PUT` | `/api/interventions/{id}/assignment` | Affecter un technicien (`responsable`/`admin`) |
| `POST` | `/api/interventions/{id}/start` | Enregistrer le début d'intervention |
| `POST` | `/api/interventions/{id}/finish` | Clôturer avec compte rendu et heure de fin |
| `POST` | `/api/interventions/{id}/cancel` | Annuler une demande non consommée |
| `GET` | `/api/interventions/{id}/parts` | Pièces demandées / utilisées |
| `POST` | `/api/interventions/{id}/parts` | Demander une pièce de rechange |
| `POST` | `/api/interventions/{id}/parts/{part_id}/use` | Consommer la pièce (sortie de stock ; `replacement_part_id` pour une pièce compatible) |
| `POST` | `/api/interventions/{id}/parts/{part_id}/cancel` | Annuler une demande de pièce en attente |
| `GET` | `/api/analytics/kpis` | MTBF, MTTR, disponibilité et coûts par équipement (`days`, `site_id`) |
| `GET` | `/api/analytics/costs` | Détail des coûts de pièces par ordre de travail |
| `GET` | `/api/analytics/alerts` | Demandes non affectées et OT préventifs en retard (`threshold_days`, `limit`) |

L'interface web exige une **connexion** (cookie de session signé, valable
7 jours). L'API reste utilisable sans session en identifiant l'utilisateur par
l'en-tête `X-GMAO-User: <identifiant>`. Les rôles (`admin`, `responsable`,
`technicien`, `lecture`) sont stockés dans `users.role` ; l'objectif reste
pédagogique (tracer *qui* saisit *quoi*), pas de constituer un annuaire
d'entreprise complet.

---

## 9. Structure du projet

```
gmao-app/
├── alembic/                  migrations (source de vérité : les modèles)
│   └── versions/
│       ├── 0001_baseline.py
│       ├── 0002_periodic_maintenance.py
│       ├── 0003_operating_hours.py
│       ├── 0004_work_orders_users_auth.py
│       ├── 0005_inventory_tools.py
│       ├── 0006_corrective_maintenance.py
│       ├── 0007_work_order_timestamps.py
│       ├── 0008_movement_costs.py
│       └── 0009_spare_part_interchanges.py
├── app/
│   ├── api/                  routes REST JSON (/api)
│   ├── models/               modèles SQLAlchemy (19 tables)
│   ├── repositories/         accès aux données (CTE récursive, pagination)
│   ├── schemas/              contrats Pydantic (entrées / sorties)
│   ├── services/             règles métier (backdating, périodicité, stock, étalonnage, corrective, analyse)
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
├── tests/                    172 tests pytest
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
- **Calcul calendaire maison** (`services/periodicity.py`) pour les
  périodicités : ajout de mois avec gestion des fins de mois, occurrences
  recalculées depuis l'ancrage (pas de dérive cumulée).
- **Périodicités en heures** : seuils calculés sur le compteur de
  l'équipement, sans date prévisionnelle ; alerte à 10 h et ligne laissée
  ouverte dans l'échéancier.
- **Journal append-only** des réalisations d'OT : l'échéance de référence et
  l'écart sont figés (ou le relevé horaire pour une règle en heures), la règle
  peut évoluer sans réécrire l'historique.

---

## 10. Tests

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
| `tests/test_periodicity.py` | calculs calendaires, libellés, rejet des heures comme unité calendaire |
| `tests/test_periodic_maintenance.py` | fournisseurs, règles de famille, échéancier calendaire et en heures, réalisations |
| `tests/test_inventory.py` | mouvements de stock append-only, seuils, suppression protégée, étalonnages calendaires, blocage des prêts, API et formulaires web |
| `tests/test_corrective_maintenance.py` | demande par tout utilisateur, affectation par le responsable, saisie des horaires et du compte rendu, pièces demandées puis consommées, stock insuffisant, annulation, API et pages web |
| `tests/test_analytics.py` | MTBF/MTTR/disponibilité, coût figé et repli sur le prix courant, pannes récurrentes, alertes, API et page d'analyse |
| `tests/test_spare_interchange.py` | compatibilités orientées, unités différentes, prix indicatif, candidats actifs, substitution à la consommation, API et pages web |

---

## 11. Suite proposée

Le socle fonctionnel couvre désormais le référentiel, l'échéancier, les
ordres de travail, les utilisateurs, l'inventaire des pièces, les fiches
d'utilisation des équipements de maintenance, la maintenance corrective et
l'analyse de fiabilité / coûts.

Pistes d'évolution :

- réserver un outil pour un OT et alerter lorsqu'un prêt dépasse la durée
  prévue ;
- proposer des campagnes d'étalonnage groupées par organisme et par échéance ;
- ajouter des exports (CSV / PDF) des fiches d'utilisation, des mouvements de
  stock et des indicateurs de maintenance ;
- suivre la main-d'œuvre (taux horaire par technicien) pour compléter le coût
  des pièces par un coût complet d'intervention.

---

## 12. Déploiement Docker (un seul conteneur)

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
| http://localhost:8000/ | Interface web (tableau de bord, après connexion) |
| http://localhost:8000/login | Connexion |
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

## 13. Historique

- **v0.1** — prototype minimal : une table `equipments` avec l'emplacement
  en texte libre.
- **v0.2** — refonte complète (ce document) : modèle WinMaint transposé,
  arborescence d'emplacements multi-usines, historique d'implantation,
  moteur de rétrodatation, API REST + interface web, migrations Alembic.
- **v0.2.1** — déploiement conteneurisé : image Docker, service unique avec
  volume de données SQLite, migrations au démarrage, sauvegarde à chaud.
- **v0.3** — inventaire : catalogue des pièces de rechange et mouvements de
  stock append-only, fiches d'utilisation des équipements de maintenance,
  étalonnages périodiques calendaires et prêts liés aux ordres de travail
  (migration `0005_inventory_tools`).
- **v0.4** — maintenance corrective : demande d'intervention par tout
  utilisateur, affectation par le responsable, saisie des heures de début et de
  fin avec compte rendu, demande puis consommation des pièces détachées avec
  sortie de stock rattachée à l'OT (migrations `0006_corrective_maintenance` et
  `0007_work_order_timestamps`).
- **v0.5** — analyse de maintenance : MTBF, MTTR et disponibilité par
  équipement, coût des pièces figé au moment du mouvement, détection des pannes
  récurrentes, page `/analytics`, API dédiée et alertes d'exploitation sur le
  tableau de bord (migration `0008_movement_costs`).
- **v0.6** — pièces de rechange compatibles : relation orientée « A remplace B »
  (migration `0009_spare_part_interchanges`), comparaison de prix indicative
  (badges « moins chère » / « plus chère »), unité identique obligatoire, choix
  délibéré d'une pièce moins chère au moment de la consommation, traçabilité de
  la pièce réellement consommée (`intervention_parts.used_spare_part_id`) et
  sortie de stock enregistrée sur la pièce substituée.
