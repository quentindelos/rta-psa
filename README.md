# rta-psa

App de recherche dans la revue technique 106/Saxo (109 pages, texte + schémas
électriques), numérisée et interrogeable via une interface web.

## Structure

- `ingestion/` — pipeline offline (OCR + embeddings via Vertex AI/Gemini), exécuté
  à la main sur les scans, jamais déployé.
- `backend/` — API FastAPI (recherche + question/réponse), sert aussi le frontend
  statique. Un seul service Cloud Run.
- `frontend/` — interface web statique (HTML/CSS/JS, sans build).
- `iac/` — infrastructure Terraform (GCP : Cloud Run, Artifact Registry, GCS, IAM,
  domain mapping).
- `.github/workflows/deploy.yml` — CI/CD : build + déploiement sur push vers `main`.

## Démarrage

### 1. Ingestion d'un lot de pages

```bash
cd ingestion
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # renseigner GOOGLE_CLOUD_PROJECT etc.
gcloud auth application-default login

python run_ingestion.py --input /chemin/vers/scans --start-page 1 --dry-run
python run_ingestion.py --input /chemin/vers/scans --start-page 1
python upload_to_gcs.py
```

### 2. Backend en local

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Ouvrir `http://localhost:8000/` — le frontend est servi directement par FastAPI
en local (voir `app/main.py`).

### 3. Infrastructure et déploiement

Voir les étapes détaillées de mise en place (création du projet GCP, activation
des APIs, service account CI, bootstrap du state Terraform, `terraform apply`,
CNAME OVH) dans le plan d'implémentation du projet.
