variable "project_id" {
  type = string
}

variable "app_name" {
  type = string
}

variable "region" {
  type = string
}

variable "domain_name" {
  type = string
}

variable "subdomain" {
  type = string
}

variable "gemini_model" {
  type = string
}

variable "embedding_model" {
  type = string
}

variable "admin_token" {
  type      = string
  sensitive = true
}
