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
4. Set `IMAGE_TAG` and optionally `API_DOMAIN_NAME`, then run the component
   deployments in order:

   ```bash
   infra/helm/deploy.sh bootstrap
   infra/helm/deploy.sh nats
   infra/helm/deploy.sh observability
   make grafana-dashboards
   infra/helm/deploy.sh grafana
   infra/helm/deploy.sh kestra
   infra/helm/deploy.sh api
   infra/helm/deploy.sh worker
   ```

Each command owns a dedicated release (`foodmind-bootstrap`, `foodmind-nats`,
and so on). During the first run it uses Helm's `--take-ownership` option to
adopt the resources from the legacy `foodmind` release without changing their
selectors. Do not subsequently upgrade or uninstall that legacy release: it
retains historical release metadata and an uninstall would delete the resources
listed in that old manifest. Keep it dormant (or remove only its Helm release
secrets after a separately reviewed cleanup procedure).

The component releases deploy API, chat worker, migrations, NATS with NUI,
Kestra, Prometheus, Tempo and Grafana. They use Workload Identity for Vertex AI,
Cloud SQL Auth Proxy for PostgreSQL, and a Kubernetes runtime secret populated at
deploy time. Kestra Basic Auth credentials are application configuration: Terraform
generates or accepts the password, stores it in Secret Manager, Helm injects it
into Kestra, and the flow-sync Job receives the same credential.
Grafana, Kestra and NUI are cluster services; expose them through an authenticated
gateway or `kubectl port-forward` rather than making operational UIs public by default.
