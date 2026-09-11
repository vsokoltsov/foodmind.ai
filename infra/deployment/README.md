# Declarative application deployment

This Terraform root manages Kubernetes bootstrap objects and the component Helm
releases. It intentionally has a separate state per component so the independent
GitHub Actions jobs can run concurrently.

Before the first deployment, apply `infra/terraform` once. That creates the
versioned state bucket, grants the GitHub Actions identity access, and publishes
the `TERRAFORM_STATE_BUCKET`, `KESTRA_PUBLIC_IP`, and `NATS_UI_PUBLIC_IP`
repository variables.

CI initializes the backend with a component-specific prefix:

```text
deploy/bootstrap
deploy/nats
deploy/observability
deploy/grafana
deploy/kestra
deploy/api
deploy/worker
```

The production migration defaults `adopt_existing_resources` to `true` so the
namespace, runtime Secret, and flow ConfigMap are imported from the former shell
deployment. Set it to `false` only when applying to a new cluster where those
objects do not exist.

Runtime credentials are fetched by the official Google Secret Manager GitHub
Action. Terraform receives them as ephemeral variables and writes them using
`kubernetes_secret_v1.data_wo`; neither the saved plan nor the GCS state retains
their values.

For a manual apply, authenticate with Application Default Credentials, provide
the same `TF_VAR_*` inputs used in `.github/workflows/deploy-component.yml`, and
run:

```text
terraform -chdir=infra/deployment init \
  -backend-config="bucket=<state-bucket>" \
  -backend-config="prefix=deploy/<component>"
terraform -chdir=infra/deployment plan -out=deployment.tfplan
terraform -chdir=infra/deployment apply deployment.tfplan
```
