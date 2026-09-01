# FoodMind infrastructure

This configuration provisions the GCS ingestion bucket and can manage the
repository GitHub Actions secret used by the LLM evaluation job. GitHub secret
management is isolated in the `modules/github-actions-secrets` module.

The GitHub provider reads `GITHUB_TOKEN` by default. The token must be allowed
to administer Actions secrets for `github_repository`. Supply the OpenAI key
through an environment variable rather than committing it:

```shell
export GITHUB_TOKEN="..."
export TF_VAR_openai_api_key="..."
terraform init
terraform apply
```

When `TF_VAR_openai_api_key` is unset, Terraform does not create or modify the
`OPENAI_API_KEY` repository secret. The key is sensitive, but Terraform state
contains the value needed to manage the resource; use encrypted remote state
and restrict access to it.
