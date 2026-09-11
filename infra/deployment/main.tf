provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_client_config" "current" {}

data "google_container_cluster" "foodmind" {
  project  = var.project_id
  name     = var.cluster_name
  location = var.region
}

locals {
  manages_runtime     = contains(["all", "bootstrap"], var.component)
  manages_kestra_flow = contains(["all", "kestra"], var.component)
  release_name        = var.component == "all" ? "foodmind" : "foodmind-${var.component}"
  chart_path          = abspath("${path.module}/../helm/foodmind")
  kestra_public_url   = "http://${var.kestra_public_ip}:8080/"
  elasticsearch_host  = trimsuffix(trimprefix(var.elasticsearch_endpoint, "https://"), "/")

  chart_values = {
    component = var.component
    images = {
      api       = "${var.artifact_registry_repository}/api:${var.image_tag}"
      kestra    = "${var.artifact_registry_repository}/kestra:${var.kestra_image_tag}"
      ingestion = "${var.artifact_registry_repository}/ingestion:${var.image_tag}"
    }
    cloudSql = {
      instanceConnectionName = var.cloud_sql_connection_name
    }
    gcpServiceAccount = var.gcp_workload_service_account
    public = {
      apiEnabled           = true
      apiHost              = var.api_domain_name
      kestraLoadBalancerIp = var.kestra_public_ip
      natsUiLoadBalancerIp = var.nats_ui_public_ip
      kestraUrl            = local.kestra_public_url
    }
    kestra = {
      basicAuthUsername = var.kestra_basic_auth_username
    }
  }
}

provider "kubernetes" {
  host                   = "https://${data.google_container_cluster.foodmind.endpoint}"
  token                  = data.google_client_config.current.access_token
  cluster_ca_certificate = base64decode(data.google_container_cluster.foodmind.master_auth[0].cluster_ca_certificate)
}

provider "helm" {
  kubernetes = {
    host                   = "https://${data.google_container_cluster.foodmind.endpoint}"
    token                  = data.google_client_config.current.access_token
    cluster_ca_certificate = base64decode(data.google_container_cluster.foodmind.master_auth[0].cluster_ca_certificate)
  }
}

resource "kubernetes_namespace_v1" "foodmind" {
  count = local.manages_runtime ? 1 : 0

  metadata {
    name = var.namespace
  }
}

resource "kubernetes_secret_v1" "runtime" {
  count = local.manages_runtime ? 1 : 0

  metadata {
    name      = "foodmind-runtime"
    namespace = var.namespace
  }

  data_wo = {
    DATABASE_URL               = "postgresql+psycopg://foodmind:${urlencode(var.foodmind_database_password)}@127.0.0.1:5432/foodmind"
    ALEMBIC_DATABASE_URL       = "postgresql+psycopg://foodmind:${urlencode(var.foodmind_database_password)}@127.0.0.1:5432/foodmind"
    KESTRA_DATABASE_URL        = "postgresql+psycopg://kestra:${urlencode(var.kestra_database_password)}@127.0.0.1:5432/kestra"
    KESTRA_POSTGRES_PASSWORD   = var.kestra_database_password
    KESTRA_BASIC_AUTH_PASSWORD = var.kestra_basic_auth_password
    ELASTICSEARCH_URL          = "https://${urlencode(var.elasticsearch_username)}:${urlencode(var.elasticsearch_password)}@${local.elasticsearch_host}"
    OPENAI_API_KEY             = var.openai_api_key
    GCP_PROJECT_ID             = var.project_id
    GCS_BUCKET                 = var.gcs_bucket
    EVALUATION_ARTIFACT_BUCKET = var.evaluation_artifact_bucket
  }
  data_wo_revision = var.runtime_secret_revision

  lifecycle {
    precondition {
      condition = alltrue([
        var.openai_api_key != "",
        var.foodmind_database_password != "",
        var.kestra_database_password != "",
        var.kestra_basic_auth_password != "",
        var.elasticsearch_password != "",
      ])
      error_message = "All runtime secret inputs must be supplied for the bootstrap component."
    }
  }

  depends_on = [kubernetes_namespace_v1.foodmind]
}

resource "kubernetes_config_map_v1" "kestra_flows" {
  count = local.manages_kestra_flow ? 1 : 0

  metadata {
    name      = "kestra-flow-definitions"
    namespace = var.namespace
  }

  data = {
    for filename in fileset("${path.module}/../kestra/flows", "*.yaml") :
    filename => file("${path.module}/../kestra/flows/${filename}")
  }
}

resource "helm_release" "foodmind" {
  name      = local.release_name
  namespace = var.namespace
  chart     = local.chart_path
  version   = "0.1.0"

  values = [yamlencode(local.chart_values)]

  atomic           = true
  cleanup_on_fail  = true
  create_namespace = true
  lint             = true
  take_ownership   = true
  timeout          = 900
  upgrade_install  = true
  wait             = true
  wait_for_jobs    = true

  depends_on = [
    kubernetes_namespace_v1.foodmind,
    kubernetes_secret_v1.runtime,
    kubernetes_config_map_v1.kestra_flows,
  ]
}

# These declarative imports migrate objects previously created by deploy.sh.
# Terraform ignores an import once the object is present in this component's
# state. Set adopt_existing_resources=false only for a new, empty cluster.
import {
  for_each = local.manages_runtime && var.adopt_existing_resources ? toset(["namespace"]) : toset([])
  to       = kubernetes_namespace_v1.foodmind[0]
  id       = var.namespace
}

import {
  for_each = local.manages_runtime && var.adopt_existing_resources ? toset(["runtime-secret"]) : toset([])
  to       = kubernetes_secret_v1.runtime[0]
  id       = "${var.namespace}/foodmind-runtime"
}

import {
  for_each = local.manages_kestra_flow && var.adopt_existing_resources ? toset(["kestra-flows"]) : toset([])
  to       = kubernetes_config_map_v1.kestra_flows[0]
  id       = "${var.namespace}/kestra-flow-definitions"
}
