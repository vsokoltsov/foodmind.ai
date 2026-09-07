#!/usr/bin/env bash
# Build or push immutable images used by the GKE Helm release and Cloud Run UI.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
terraform_directory="${project_root}/infra/terraform"
image_tag="${IMAGE_TAG:?Set IMAGE_TAG (for example, a Git commit SHA).}"
repository="${ARTIFACT_REGISTRY_REPOSITORY:-$(terraform -chdir="${terraform_directory}" output -raw artifact_registry_repository)}"
region="${GCP_REGION:-europe-west3}"
target_platform="${CONTAINER_PLATFORM:-linux/amd64}"
operation="${1:-all}"

case "${operation}" in
  build)
    docker build --platform="${target_platform}" -f "${project_root}/Dockerfile.api" -t "${repository}/api:${image_tag}" "${project_root}"
    docker build --platform="${target_platform}" -f "${project_root}/Dockerfile.kestra" -t "${repository}/kestra:${image_tag}" "${project_root}"
    docker build --platform="${target_platform}" -f "${project_root}/Dockerfile.ui" -t "${repository}/ui:${image_tag}" "${project_root}"
    docker tag "${repository}/ui:${image_tag}" "${repository}/ui:latest"
    ;;
  push)
    gcloud auth configure-docker "${region}-docker.pkg.dev" --quiet
    docker push "${repository}/api:${image_tag}"
    docker push "${repository}/kestra:${image_tag}"
    docker push "${repository}/ui:${image_tag}"
    docker push "${repository}/ui:latest"
    ;;
  all)
    "${BASH_SOURCE[0]}" build
    "${BASH_SOURCE[0]}" push
    ;;
  *)
    echo "Usage: $0 [build|push|all]" >&2
    exit 2
    ;;
esac
