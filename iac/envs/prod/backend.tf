terraform {
  backend "gcs" {
    bucket = "rta-psa-terraform-state"
    prefix = "rta-psa/envs/prod"
  }
}
