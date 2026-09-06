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
}
