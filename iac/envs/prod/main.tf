module "services" {
  source          = "../../modules/services"
  project_id      = var.project_id
  app_name        = var.app_name
  region          = var.region
  domain_name     = var.domain_name
  subdomain       = var.subdomain
  gemini_model    = var.gemini_model
  embedding_model = var.embedding_model
  admin_token     = var.admin_token
}
