# FoodMind infrastructure

This configuration provisions the GCS ingestion and Terraform-state buckets,
Vertex AI access, Google
Secret Manager secrets for the OpenAI and Gemini API keys, and GitHub Actions
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
