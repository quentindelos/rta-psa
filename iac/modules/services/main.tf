resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = "${var.app_name}-repo"
  description   = "Dépôt Docker pour l'app rta-psa"
  format        = "DOCKER"
}

# Pages scannées : lecture publique pour que le frontend pointe directement
# dessus en <img>, sans proxy ni CORS.
resource "google_storage_bucket" "pages" {
  name                        = "${var.app_name}-pages"
  location                    = var.region
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_iam_member" "pages_public_read" {
  bucket = google_storage_bucket.pages.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Index (metadata + embeddings) : privé, lu uniquement par le service Cloud Run.
resource "google_storage_bucket" "index" {
  name                        = "${var.app_name}-index"
  location                    = var.region
  uniform_bucket_level_access = true
}

resource "google_service_account" "run_sa" {
  account_id   = "${var.app_name}-run"
  display_name = "Service account d'exécution Cloud Run pour rta-psa"
}

resource "google_storage_bucket_iam_member" "run_sa_reads_index" {
  bucket = google_storage_bucket.index.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.run_sa.email}"
}

resource "google_project_iam_member" "run_sa_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.run_sa.email}"
}

# Jeton admin de /api/admin/reload-index : stocké dans Secret Manager plutôt
# qu'en variable d'environnement en clair (visible sinon dans la console Cloud
# Run et via `gcloud run services describe` par quiconque a un accès lecture).
resource "google_secret_manager_secret" "admin_token" {
  secret_id = "${var.app_name}-admin-token"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "admin_token" {
  secret      = google_secret_manager_secret.admin_token.id
  secret_data = var.admin_token
}

resource "google_secret_manager_secret_iam_member" "run_sa_reads_admin_token" {
  secret_id = google_secret_manager_secret.admin_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run_sa.email}"
}

resource "google_cloud_run_v2_service" "app" {
  name     = var.app_name
  location = var.region

  template {
    service_account = google_service_account.run_sa.email

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_REGION"
        value = var.region
      }
      env {
        name  = "GCS_BUCKET_PAGES"
        value = google_storage_bucket.pages.name
      }
      env {
        name  = "GCS_BUCKET_INDEX"
        value = google_storage_bucket.index.name
      }
      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "EMBEDDING_MODEL"
        value = var.embedding_model
      }
      env {
        name = "ADMIN_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.admin_token.secret_id
            version = "latest"
          }
        }
      }
    }

    scaling {
      min_instance_count = 0
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image
    ]
  }

  depends_on = [
    google_storage_bucket_iam_member.run_sa_reads_index,
    google_project_iam_member.run_sa_vertex_user,
    google_secret_manager_secret_iam_member.run_sa_reads_admin_token,
  ]
}

resource "google_cloud_run_service_iam_member" "app_public" {
  location = google_cloud_run_v2_service.app.location
  service  = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Volontairement absent tant que la bascule DNS n'est pas faite : le même
# domaine est encore mappé sur le service de l'ancien projet GCP "rta-psa",
# et Google Cloud Run n'autorise pas un domaine mappé sur deux services en
# même temps. À réactiver au moment de la coupure (voir migration).
#
# resource "google_cloud_run_domain_mapping" "app_dns" {
#   location = var.region
#   name     = "${var.subdomain}.${var.domain_name}"
#
#   metadata {
#     namespace = var.project_id
#   }
#
#   spec {
#     route_name = google_cloud_run_v2_service.app.name
#   }
# }
