"""Upload manuel des images de pages et de l'index vers GCS.

À lancer à la main après avoir relu la sortie de run_ingestion.py — l'ingestion ne
déclenche jamais d'upload/déploiement automatique.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import config


def rsync(src: Path, dest: str) -> None:
    print(f"→ gcloud storage rsync {src} {dest} (miroir exact, supprime le superflu côté GCS)")
    subprocess.run(
        [
            "gcloud",
            "storage",
            "rsync",
            "--recursive",
            "--delete-unmatched-destination-objects",
            str(src),
            dest,
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path("data"))
    parser.add_argument("--pages-bucket", default=None, help="Par défaut : GCS_BUCKET_PAGES de la config")
    parser.add_argument("--index-bucket", default=None, help="Par défaut : GCS_BUCKET_INDEX de la config")
    args = parser.parse_args()

    cfg = config.load_config()
    pages_bucket = args.pages_bucket or cfg.gcs_bucket_pages
    index_bucket = args.index_bucket or cfg.gcs_bucket_index

    rsync(args.workdir / "pages", f"gs://{pages_bucket}/")
    rsync(args.workdir / "index", f"gs://{index_bucket}/index/")

    print("✓ Upload terminé.")


if __name__ == "__main__":
    main()
