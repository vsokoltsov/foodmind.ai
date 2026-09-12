data "ec_deployment_templates" "available" {
  region          = var.region
  stack_version   = var.elastic_stack_version
  show_deprecated = false
}

locals {
  available_deployment_templates = {
    for template in data.ec_deployment_templates.available.templates :
    template.id => template.name
  }
}

resource "ec_deployment" "foodmind" {
  name                   = var.name
  region                 = var.region
  version                = var.elastic_stack_version
  deployment_template_id = var.deployment_template_id

  elasticsearch = {
    hot = {
      autoscaling = {}
    }
  }
  kibana = {}

  lifecycle {
    precondition {
      condition     = contains(keys(local.available_deployment_templates), var.deployment_template_id)
      error_message = "Elastic deployment template '${var.deployment_template_id}' is unavailable, deprecated, or incompatible with ${var.elastic_stack_version} in ${var.region}. Available templates: ${jsonencode(local.available_deployment_templates)}"
    }
  }
}
