# GKE deployment

Terraform in `infra/terraform` creates the Google Cloud network, GKE cluster,
Artifact Registry, Cloud SQL, Cloud Run UI, Vertex AI access, and managed
Elasticsearch/Kibana in Elastic Cloud. Elastic Cloud is used because Google Cloud
has no native managed Elasticsearch offering.

1. Run `EC_API_KEY=... infra/terraform/list-elastic-templates.sh gcp-europe-west3`,
   choose a listed non-deprecated template ID, and apply `infra/terraform` with
   that ID and `elastic_cloud_api_key` in its local `terraform.tfvars`.
2. Build and push immutable images with
   `IMAGE_TAG=<git-sha> infra/deploy/build-images.sh`.
3. Run Terraform again with `ui_image` set to that pushed UI image, the
   API URL, and a verified Cloud Run domain.
4. Set `IMAGE_TAG` and optionally `API_DOMAIN_NAME`, then run `infra/helm/deploy.sh`.

The Helm release deploys API, chat worker, migrations, NATS with NUI, Kestra,
Prometheus, Tempo and Grafana. It uses Workload Identity for Vertex AI, Cloud SQL
Auth Proxy for PostgreSQL, and a Kubernetes runtime secret populated at deploy time.
Grafana, Kestra and NUI are cluster services; expose them through an authenticated
gateway or `kubectl port-forward` rather than making operational UIs public by default.
