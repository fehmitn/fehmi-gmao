# GMAO

Application de gestion de maintenance assistée par ordinateur.

Stack actuelle : Python, FastAPI, SQLAlchemy 2, SQLite.

## Architecture

```
app/
  models/        # tables SQLAlchemy
  schemas/       # contrats d'entrée/sortie (Pydantic)
  repositories/  # accès base de données
  services/      # règles métier
  api/           # routes HTTP
```

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Lancer l'API

```powershell
uvicorn app.main:app --reload
```

Documentation interactive : http://127.0.0.1:8000/docs

## Ajouter un équipement

```powershell
curl -X POST http://127.0.0.1:8000/equipments `
  -H "Content-Type: application/json" `
  -d "{\"code\":\"EQ-001\",\"name\":\"Pompe centrifuge P-12\",\"category\":\"Pompe\",\"location\":\"Atelier A\"}"
```
