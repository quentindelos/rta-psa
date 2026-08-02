terraform {
  backend "gcs" {
    bucket = "rta-psa-tfstate"
    prefix = "rta-psa/envs/prod"
  }
}
