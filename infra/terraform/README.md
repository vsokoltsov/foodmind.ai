# FoodMind infrastructure

This configuration provisions the GCS ingestion and Terraform-state buckets,
Vertex AI access, Google Secret Manager secrets for the OpenAI and Gemini API
keys, and GitHub Actions
Workload Identity Federation. GitHub Actions receives only non-sensitive
connection identifiers as repository variables and reads `OPENAI_API_KEY` from
Secret Manager at runtime. Vertex AI is accessed with service-account
credentials (Application Default Credentials), not a long-lived API key.

The GitHub provider reads `GITHUB_TOKEN` by default. The token must be allowed
to administer repository Actions variables. Supply the OpenAI key through an
environment variable rather than committing it:

```shell
export GITHUB_TOKEN="..."
export TF_VAR_openai_api_key="..."
export TF_VAR_gemini_api_key="..."
terraform init
terraform apply
```

When either API-key variable is unset, Terraform does not create that secret.
The keys are sensitive, and Terraform state contains the secret version values;
use encrypted remote state and restrict access to it. GitHub Actions exchanges
its OIDC token for short-lived Google credentials, so no service-account JSON
key is stored in GitHub.

Apply this root before using `infra/deployment`. It publishes the state-bucket
and static-IP repository variables consumed by the declarative component
deployment workflow.

The Elastic provider queries deployment templates for the configured region and
stack version during planning. Deprecated templates are excluded, and the plan
fails with the compatible ID/name map when
`elastic_cloud_deployment_template_id` is invalid. After a successful refresh
or apply, the same map is available as:

```shell
terraform output elastic_cloud_available_deployment_templates
```

## Complete teardown

The Kubernetes releases use independent Terraform states, while this
infrastructure root owns the GKE cluster, Cloud SQL, Elastic Cloud, networking,
Artifact Registry, Secret Manager resources, Cloud Run, and GCS buckets. They
must be destroyed in that order so Kubernetes controllers can release load
balancers and persistent disks before GKE and its VPC disappear.

First, update the live resources with the explicit teardown profile. This
disables both GKE deletion protection and the two Cloud SQL deletion-protection
layers, and enables deletion of every object version in the artifact and
component-state buckets:

```shell
terraform -chdir=infra/terraform apply -var-file=destroy.tfvars
```

Next, run the **Destroy application deployment** workflow and enter
`DESTROY foodmind`. It destroys the isolated states sequentially, leaves the
bootstrap namespace until last, and also checks the historical `deploy/all`
state. Do not start the infrastructure destroy until that workflow succeeds.

Finally, destroy the infrastructure root from the same checkout and local state
used to create it:

```shell
terraform -chdir=infra/terraform plan -destroy \
  -var-file=destroy.tfvars \
  -out=destroy.tfplan
terraform -chdir=infra/terraform apply destroy.tfplan
```

The Cloud SQL databases and users already reference their instance, so
Terraform deletes them before the instance automatically. The Cloud SQL
instance in turn depends on private service networking, which keeps the
connection and VPC alive until the database is gone.

This process permanently deletes databases, Elasticsearch data, bucket objects
and object versions, container images, persistent volumes, secrets, and
component state. The infrastructure root intentionally uses local state because
its managed GCS bucket contains the component states and must itself be deleted
at the end. Preserve `infra/terraform/terraform.tfstate` until the final apply
has completed.
