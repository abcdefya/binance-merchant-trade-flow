# ------------------------------LOGGING BUCKET
resource "google_storage_bucket" "logging_bucket" {
  name          = var.logging_bucket
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
  depends_on = [google_container_cluster.gke-cluster]
}

# Grant Airflow GCS logger service account access to the logging bucket
resource "google_storage_bucket_iam_member" "airflow_gcs_logger_access" {
  bucket = google_storage_bucket.logging_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.airflow_gcs_logger.email}"
  
  depends_on = [
    google_storage_bucket.logging_bucket,
    google_service_account.airflow_gcs_logger
  ]
}

# ------------------------------GOLD BUCKET
resource "google_storage_bucket" "gold_bucket" {
  name          = var.gold_bucket
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true
  depends_on = [google_container_cluster.gke-cluster]
}

# ------------------------------ARTIFACT REGISTRY
resource "google_artifact_registry_repository" "docker_repo" {
  location      = var.region
  repository_id = var.artifact_registry_repository
  description    = "Docker repository for container images"
  format         = "DOCKER"
}