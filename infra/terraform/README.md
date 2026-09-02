# FoodMind infrastructure

This configuration provisions the GCS ingestion bucket, a Google Secret
Manager secret for the LLM evaluation key, and GitHub Actions Workload
Identity Federation. GitHub Actions receives only non-sensitive connection
identifiers as repository variables and reads `OPENAI_API_KEY` from Secret
Manager at runtime.

The GitHub provider reads `GITHUB_TOKEN` by default. The token must be allowed
to administer repository Actions variables. Supply the OpenAI key through an
environment variable rather than committing it:

```shell
export GITHUB_TOKEN="..."
export TF_VAR_openai_api_key="..."
terraform init
terraform apply
```

When `TF_VAR_openai_api_key` is unset, Terraform does not create the secret.
The key is sensitive, and Terraform state contains the secret version value;
use encrypted remote state and restrict access to it. GitHub Actions exchanges
its OIDC token for short-lived Google credentials, so no service-account JSON
key is stored in GitHub.
