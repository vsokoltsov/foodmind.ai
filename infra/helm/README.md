# FoodMind Helm chart

The chart is deployed by the declarative Terraform root in `infra/deployment`.
Do not invoke `helm upgrade` directly: each component is a Terraform-managed
Helm release with an isolated GCS state prefix.

GitHub Actions deploys the component states in this order:

1. `bootstrap` (namespace, runtime Secret, service account, migrations)
2. `nats`, `observability`, `grafana`, `kestra`, `api`, and `worker`

Each state owns a dedicated release (`foodmind-bootstrap`, `foodmind-nats`, and
so on). The first apply uses Helm upgrade mode and ownership adoption for the
existing releases. Terraform import blocks adopt the namespace, runtime Secret,
and Kestra flow ConfigMap previously created by the legacy script. For a new,
empty cluster set `adopt_existing_resources=false`.

The releases deploy API, chat worker, migrations, NATS with NUI, Kestra,
Prometheus, Tempo, and Grafana. They use Workload Identity for Vertex AI, Cloud
SQL Auth Proxy for PostgreSQL, and a Kubernetes runtime Secret populated during
the bootstrap apply. Secret Manager values enter Terraform as ephemeral
variables and the Kubernetes provider writes them through a write-only field,
so they are not retained in the deployment plan or state.

Grafana, Kestra, and NUI are publicly reachable operational services in the
current review environment. Production deployments should place them behind an
authenticated gateway.
