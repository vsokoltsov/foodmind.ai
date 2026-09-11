#!/usr/bin/env bash
# Deploy the stateful FoodMind backend stack to a provisioned GKE cluster.
#
# Required tools: gcloud, kubectl, helm, jq, and python/uv. Terraform is needed
# only when the deployment coordinates are not supplied through environment variables.
# The script deliberately does not call terraform apply: infrastructure changes
# remain an explicit, reviewable operation.
set -euo pipefail

component="${1:-all}"
case "${component}" in
  all|bootstrap|nats|observability|grafana|kestra|api|worker) ;;
  *)
    echo "Unknown component '${component}'. Expected all, bootstrap, nats, observability, grafana, kestra, api, or worker." >&2
    exit 2
    ;;
esac

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
terraform_directory="${project_root}/infra/terraform"
chart_directory="${project_root}/infra/helm/foodmind"
namespace="${FOODMIND_NAMESPACE:-${GKE_NAMESPACE:-foodmind}}"
image_tag="${IMAGE_TAG:?Set IMAGE_TAG to an immutable image tag.}"

tf_output() {
  terraform -chdir="${terraform_directory}" output -raw "$1"
}

value_from_environment_or_terraform() {
  local environment_name="$1"
  local terraform_output_name="$2"

  if [[ -n "${!environment_name:-}" ]]; then
    printf '%s' "${!environment_name}"
    return
  fi

  tf_output "${terraform_output_name}"
}

project_id="${GCP_PROJECT_ID:-$(tf_output project_id 2>/dev/null || true)}"
if [[ -z "${project_id}" ]]; then
  project_id="$(terraform -chdir="${terraform_directory}" console <<< 'var.project_id' | tr -d '"')"
fi
region="${GCP_REGION:-europe-west3}"
repository="$(value_from_environment_or_terraform ARTIFACT_REGISTRY_REPOSITORY artifact_registry_repository)"
cluster="$(value_from_environment_or_terraform GKE_CLUSTER_NAME gke_cluster_name)"
cloud_sql="$(value_from_environment_or_terraform CLOUD_SQL_CONNECTION_NAME cloud_sql_connection_name)"
gcp_service_account="$(value_from_environment_or_terraform GCP_WORKLOAD_SERVICE_ACCOUNT gke_workload_service_account_email)"
foodmind_password="$(value_from_environment_or_terraform FOODMIND_DATABASE_PASSWORD cloud_sql_foodmind_password)"
kestra_password="$(value_from_environment_or_terraform KESTRA_DATABASE_PASSWORD cloud_sql_kestra_password)"
# The username is deliberately non-secret and stable. Unlike the password it
# does not need Terraform state or Secret Manager access in a deployment job.
kestra_basic_auth_username="${KESTRA_BASIC_AUTH_USERNAME:-admin@foodmind.local}"
kestra_basic_auth_password="${KESTRA_BASIC_AUTH_PASSWORD:?Set KESTRA_BASIC_AUTH_PASSWORD.}"
elasticsearch_endpoint="$(value_from_environment_or_terraform ELASTICSEARCH_ENDPOINT elasticsearch_endpoint)"
elasticsearch_username="$(value_from_environment_or_terraform ELASTICSEARCH_USERNAME elasticsearch_username)"
elasticsearch_password="$(value_from_environment_or_terraform ELASTICSEARCH_PASSWORD elasticsearch_password)"
gcs_bucket="$(value_from_environment_or_terraform GCS_BUCKET artifact_bucket_name)"
evaluation_bucket="${EVALUATION_ARTIFACT_BUCKET:-$(tf_output evaluation_artifact_bucket_name 2>/dev/null || true)}"
openai_key="${OPENAI_API_KEY:-$(gcloud secrets versions access latest --secret=OPENAI_API_KEY --project="${project_id}")}"

if [[ -z "${elasticsearch_endpoint}" || -z "${elasticsearch_username}" || -z "${elasticsearch_password}" ]]; then
  echo "Elastic Cloud outputs are missing. Apply the main Terraform root first." >&2
  exit 1
fi

api_image="${repository}/api:${image_tag}"
kestra_image="${repository}/kestra:${KESTRA_IMAGE_TAG:-${image_tag}}"
ingestion_image="${repository}/ingestion:${INGESTION_IMAGE_TAG:-${image_tag}}"

case "${component}" in
  all) release_name="foodmind" ;;
  *) release_name="foodmind-${component}" ;;
esac

gcloud container clusters get-credentials "${cluster}" --region "${region}" --project "${project_id}"
kubectl create namespace "${namespace}" --dry-run=client -o yaml | kubectl apply -f -

# The regional addresses are provisioned by Terraform. CI can resolve them
# directly instead of needing read access to the Terraform state.
kestra_public_ip="${KESTRA_PUBLIC_IP:-$(gcloud compute addresses describe "${cluster}-kestra-ip" --region "${region}" --project "${project_id}" --format='value(address)')}"
nats_ui_public_ip="${NATS_UI_PUBLIC_IP:-$(gcloud compute addresses describe "${cluster}-nats-ui-ip" --region "${region}" --project "${project_id}" --format='value(address)')}"

database_url="postgresql+psycopg://foodmind:${foodmind_password}@127.0.0.1:5432/foodmind"
kestra_database_url="postgresql+psycopg://kestra:${kestra_password}@127.0.0.1:5432/kestra"
# Elastic Cloud exposes a credential-free HTTPS endpoint. Normalize its scheme
# and optional trailing slash before it becomes the authority section of a URL.
elasticsearch_authority="${elasticsearch_endpoint#https://}"
elasticsearch_authority="${elasticsearch_authority#http://}"
elasticsearch_authority="${elasticsearch_authority%/}"
if [[ -z "${elasticsearch_authority}" || "${elasticsearch_authority}" == *[@/?#]* ]]; then
  echo "ELASTICSEARCH_ENDPOINT must be a credential-free HTTPS host and optional port." >&2
  exit 1
fi

# Elastic Cloud credentials may contain URL-reserved characters such as ``@``
# or ``#``. Percent-encode them before constructing the connection URL; without
# this, HTTP clients can interpret a portion of the password as the hostname.
elasticsearch_username_encoded="$(printf '%s' "${elasticsearch_username}" | jq -sRr '@uri')"
elasticsearch_password_encoded="$(printf '%s' "${elasticsearch_password}" | jq -sRr '@uri')"
elasticsearch_url="https://${elasticsearch_username_encoded}:${elasticsearch_password_encoded}@${elasticsearch_authority}"

kubectl -n "${namespace}" create secret generic foodmind-runtime \
  --from-literal=DATABASE_URL="${database_url}" \
  --from-literal=ALEMBIC_DATABASE_URL="${database_url}" \
  --from-literal=KESTRA_DATABASE_URL="${kestra_database_url}" \
  --from-literal=KESTRA_POSTGRES_PASSWORD="${kestra_password}" \
  --from-literal=KESTRA_BASIC_AUTH_PASSWORD="${kestra_basic_auth_password}" \
  --from-literal=ELASTICSEARCH_URL="${elasticsearch_url}" \
  --from-literal=OPENAI_API_KEY="${openai_key}" \
  --from-literal=GCP_PROJECT_ID="${project_id}" \
  --from-literal=GCS_BUCKET="${gcs_bucket}" \
  --from-literal=EVALUATION_ARTIFACT_BUCKET="${evaluation_bucket}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Flows are source artifacts, not image configuration. Mount the checked-in
# definitions into the synchronization hook so a flow-only deployment takes
# effect immediately and cannot accidentally use definitions baked into an
# older Kestra image.
kubectl -n "${namespace}" create configmap kestra-flow-definitions \
  --from-file="${project_root}/infra/kestra/flows" \
  --dry-run=client -o yaml | kubectl apply -f -

# Kestra is exposed by a dedicated LoadBalancer service on port 8080, not
# through the API ingress on port 80. Keep generated links and redirects
# consistent with the externally reachable endpoint.
kestra_public_url="http://${kestra_public_ip}:8080/"

helm upgrade --install "${release_name}" "${chart_directory}" \
  --namespace "${namespace}" \
  --set-string component="${component}" \
  --set-string images.api="${api_image}" \
  --set-string images.kestra="${kestra_image}" \
  --set-string images.ingestion="${ingestion_image}" \
  --set-string cloudSql.instanceConnectionName="${cloud_sql}" \
  --set-string gcpServiceAccount="${gcp_service_account}" \
  --set public.apiEnabled=true \
  --set-string public.apiHost="${API_DOMAIN_NAME:-}" \
  --set-string public.kestraLoadBalancerIp="${kestra_public_ip}" \
  --set-string public.natsUiLoadBalancerIp="${nats_ui_public_ip}" \
  --set-string public.kestraUrl="${kestra_public_url}" \
  --set-string kestra.basicAuthUsername="${kestra_basic_auth_username}" \
  --take-ownership \
  --force-conflicts \
  --wait --timeout 15m

if [[ "${component}" != "all" ]]; then
  echo "Deployed ${component} as Helm release ${release_name}."
fi
