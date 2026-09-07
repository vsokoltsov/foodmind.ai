#!/usr/bin/env bash
# Build or push immutable images used by the GKE Helm release and Cloud Run UI.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
terraform_directory="${project_root}/infra/terraform"
operation="${1:-all}"
image_tag="${IMAGE_TAG:-}"
if [[ "${operation}" != "dependencies" && -z "${image_tag}" ]]; then
  echo "Set IMAGE_TAG (for example, a Git commit SHA)." >&2
  exit 2
fi
repository="${ARTIFACT_REGISTRY_REPOSITORY:-$(terraform -chdir="${terraform_directory}" output -raw artifact_registry_repository)}"
region="${GCP_REGION:-europe-west3}"
target_platform="${CONTAINER_PLATFORM:-linux/amd64}"
dependency_image="${PYTHON_BASE_IMAGE:-${repository}/python-dependencies:local}"

build_image() {
  local dockerfile="$1"
  local image="$2"
  local cache_scope="$3"
  local publish="${4:-false}"

  local -a build_args=()
  local -a output_args=(--load)
  if [[ "${dockerfile}" == "Dockerfile.api" || "${dockerfile}" == "Dockerfile.ui" ]]; then
    build_args+=(--build-arg "PYTHON_BASE_IMAGE=${dependency_image}")
  fi
  if [[ "${publish}" == "true" ]]; then
    output_args=(--push)
  fi

  if [[ "${GITHUB_ACTIONS:-false}" == "true" ]]; then
    docker buildx build \
      --platform="${target_platform}" \
      --cache-from="type=gha,scope=${cache_scope}" \
      --cache-to="type=gha,mode=max,scope=${cache_scope}" \
      "${output_args[@]}" \
      "${build_args[@]}" \
      -f "${project_root}/${dockerfile}" \
      -t "${image}" \
      "${project_root}"
    return
  fi

  if [[ "${publish}" == "true" ]]; then
    docker buildx build \
      --platform="${target_platform}" \
      "${build_args[@]}" \
      --push \
      -f "${project_root}/${dockerfile}" \
      -t "${image}" \
      "${project_root}"
    return
  fi

  docker build \
    --platform="${target_platform}" \
    "${build_args[@]}" \
    -f "${project_root}/${dockerfile}" \
    -t "${image}" \
    "${project_root}"
}

build_dependencies() {
  local cache_scope="foodmind-python-dependencies"
  local -a output_args=(--load)
  if [[ "${PUSH_DEPENDENCY_IMAGE:-false}" == "true" ]]; then
    output_args=(--push)
  fi

  if [[ "${GITHUB_ACTIONS:-false}" == "true" ]]; then
    docker buildx build \
      --platform="${target_platform}" \
      --cache-from="type=gha,scope=${cache_scope}" \
      --cache-to="type=gha,mode=max,scope=${cache_scope}" \
      "${output_args[@]}" \
      -f "${project_root}/Dockerfile.python-base" \
      -t "${dependency_image}" \
      "${project_root}"
    return
  fi

  docker build \
    --platform="${target_platform}" \
    -f "${project_root}/Dockerfile.python-base" \
    -t "${dependency_image}" \
    "${project_root}"
}

case "${operation}" in
  dependencies)
    build_dependencies
    ;;
  build)
    build_image "Dockerfile.api" "${repository}/api:${image_tag}" "foodmind-api"
    build_image "Dockerfile.kestra" "${repository}/kestra:${image_tag}" "foodmind-kestra"
    build_image "Dockerfile.ui" "${repository}/ui:${image_tag}" "foodmind-ui"
    docker tag "${repository}/ui:${image_tag}" "${repository}/ui:latest"
    ;;
  api)
    build_image "Dockerfile.api" "${repository}/api:${image_tag}" "foodmind-api"
    ;;
  kestra)
    build_image "Dockerfile.kestra" "${repository}/kestra:${image_tag}" "foodmind-kestra"
    ;;
  ui)
    build_image "Dockerfile.ui" "${repository}/ui:${image_tag}" "foodmind-ui"
    docker tag "${repository}/ui:${image_tag}" "${repository}/ui:latest"
    ;;
  publish-api)
    build_image "Dockerfile.api" "${repository}/api:${image_tag}" "foodmind-api" true
    ;;
  publish-kestra)
    build_image "Dockerfile.kestra" "${repository}/kestra:${image_tag}" "foodmind-kestra" true
    ;;
  publish-ui)
    build_image "Dockerfile.ui" "${repository}/ui:${image_tag}" "foodmind-ui" true
    docker buildx imagetools create \
      --tag "${repository}/ui:latest" \
      "${repository}/ui:${image_tag}"
    ;;
  push)
    gcloud auth configure-docker "${region}-docker.pkg.dev" --quiet
    docker push "${repository}/api:${image_tag}"
    docker push "${repository}/kestra:${image_tag}"
    docker push "${repository}/ui:${image_tag}"
    docker push "${repository}/ui:latest"
    ;;
  push-api)
    gcloud auth configure-docker "${region}-docker.pkg.dev" --quiet
    docker push "${repository}/api:${image_tag}"
    ;;
  push-kestra)
    gcloud auth configure-docker "${region}-docker.pkg.dev" --quiet
    docker push "${repository}/kestra:${image_tag}"
    ;;
  push-ui)
    gcloud auth configure-docker "${region}-docker.pkg.dev" --quiet
    docker push "${repository}/ui:${image_tag}"
    docker push "${repository}/ui:latest"
    ;;
  all)
    "${BASH_SOURCE[0]}" dependencies
    "${BASH_SOURCE[0]}" build
    "${BASH_SOURCE[0]}" push
    ;;
  *)
    echo "Usage: $0 [dependencies|build|api|kestra|ui|publish-api|publish-kestra|publish-ui|push|push-api|push-kestra|push-ui|all]" >&2
    exit 2
    ;;
esac
