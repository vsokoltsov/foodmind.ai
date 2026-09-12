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

The Cloud SQL databases are deleted before their instance. PostgreSQL refuses
to drop application roles while those roles still own schema objects, so the
two `google_sql_user` resources use `deletion_policy = "ABANDON"`. Terraform
forgets the user resources without issuing `DROP ROLE`; deleting the Cloud SQL
instance then removes the users and their objects together. The instance in
turn depends on private service networking, which keeps the connection and VPC
alive until the database is gone.

Terraform also leaves project APIs enabled when their resources leave state.
Disabling foundational APIs such as IAM during teardown can fail while GKE or
Google-managed services still depend on them, and disabling APIs is not
necessary to remove FoodMind resources.

This process permanently deletes databases, Elasticsearch data, bucket objects
and object versions, container images, persistent volumes, secrets, and
component state. The infrastructure root intentionally uses local state because
its managed GCS bucket contains the component states and must itself be deleted
at the end. Preserve `infra/terraform/terraform.tfstate` until the final apply
has completed.

### Retrying a partially completed destroy

If a destroy started with an older configuration and failed while disabling an
API or deleting a PostgreSQL user, persist only the corrected lifecycle fields
before making a new destroy plan. A full apply could recreate resources already
removed by the partial destroy, so use these targets:

```shell
terraform -chdir=infra/terraform apply \
  -var-file=destroy.tfvars \
  -target=google_project_service.secret_manager \
  -target=google_project_service.iam \
  -target=google_project_service.iam_credentials \
  -target=google_project_service.sts \
  -target=module.cloud_sql.google_sql_user.foodmind \
  -target=module.cloud_sql.google_sql_user.kestra
```

Discard the failed saved plan, create a new `plan -destroy` with
`destroy.tfvars`, inspect it, and apply the new plan. Terraform will abandon the
two SQL-user resources, leave the project APIs enabled, and continue deleting
the Cloud SQL instance and remaining infrastructure.
