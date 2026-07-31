variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "europe-west1"
}

variable "domain_name" {
  type = string
}

variable "subdomain" {
  type = string
}

variable "tfstate_bucket_name" {
  type = string
}

variable "gemini_model" {
  type    = string
  default = "gemini-2.5-flash"
}

variable "embedding_model" {
  type    = string
  default = "text-multilingual-embedding-002"
}

variable "admin_token" {
  type      = string
  sensitive = true
}
