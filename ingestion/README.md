# Ingestion

Pipeline offline exécuté à la main sur ta machine, jamais déployé. Transforme des
scans (PDF ou photos iPhone) en un index cherchable (texte OCR + description des
schémas électriques + embeddings) uploadé sur GCS.

## Installation

```bash
cd ingestion
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # renseigner GOOGLE_CLOUD_PROJECT etc.
gcloud auth application-default login
```

## Utilisation

```bash
# 1. Vérifier le découpage en pages sans dépenser d'appels Gemini
python run_ingestion.py --input /chemin/vers/manuel.pdf --start-page 1 --dry-run

# 2. Lancer l'ingestion réelle (OCR + embeddings) sur un lot
python run_ingestion.py --input /chemin/vers/manuel.pdf --start-page 1

# Relancer la même commande est un no-op rapide : les pages déjà indexées
# (voir data/index/manifest.json) ne sont jamais retraitées, sauf --force.

# 3. Upload vers GCS (étape manuelle, séparée)
python upload_to_gcs.py
```

Pour un dossier de photos iPhone scannées dans le désordre ou avec des reprises,
utiliser `--page-map pages.csv` (colonnes `filename,page_num`) plutôt que
`--start-page`.

Après l'upload, appeler `POST /api/admin/reload-index` sur le backend déployé
pour qu'il recharge l'index sans attendre un redémarrage naturel du conteneur.
