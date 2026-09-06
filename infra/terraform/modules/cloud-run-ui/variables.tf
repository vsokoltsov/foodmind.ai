variable "project_id" { type = string }
variable "region" { type = string }
variable "name" { type = string }
variable "image" { type = string }
variable "api_url" { type = string }
variable "nicegui_secret_id" { type = string }
variable "public_access" { type = bool }
variable "dns_managed_zone" {
  type     = string
  default  = null
  nullable = true
}
variable "domain_name" {
  type     = string
  default  = null
  nullable = true
}
