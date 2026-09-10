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

authenticate_artifact_registry() {
  """Log Docker into Artifact Registry with a retried short-lived access token."""
  local registry="${region}-docker.pkg.dev"
  local attempt
  local access_token

  # `gcloud auth configure-docker` installs a credential helper which fetches a
  # new Workload Identity token for every BuildKit registry request.  That made
  # image builds fail when a single token request was reset by the network.
  # A normal Docker login gives BuildKit one temporary token for this build.
  for attempt in 1 2 3 4 5; do
    if access_token="$(gcloud auth print-access-token)" && \
      printf '%s' "${access_token}" | \
        docker login --username=oauth2accesstoken --password-stdin "https://${registry}"; then
      return 0
    fi
    echo "Artifact Registry authentication attempt ${attempt}/5 failed; retrying..." >&2
    sleep "${attempt}"
  done

  echo "Unable to authenticate Docker with Artifact Registry after 5 attempts." >&2
  return 1
}

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
    if [[ "${PUSH_DEPENDENCY_IMAGE:-false}" == "true" ]]; then
      authenticate_artifact_registry
    fi
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
    authenticate_artifact_registry
    build_image "Dockerfile.api" "${repository}/api:${image_tag}" "foodmind-api" true
    ;;
  publish-kestra)
    authenticate_artifact_registry
    build_image "Dockerfile.kestra" "${repository}/kestra:${image_tag}" "foodmind-kestra" true
    ;;
  publish-ui)
    authenticate_artifact_registry
    build_image "Dockerfile.ui" "${repository}/ui:${image_tag}" "foodmind-ui" true
    docker buildx imagetools create \
      --tag "${repository}/ui:latest" \
      "${repository}/ui:${image_tag}"
    ;;
  push)
    authenticate_artifact_registry
    docker push "${repository}/api:${image_tag}"
    docker push "${repository}/kestra:${image_tag}"
    docker push "${repository}/ui:${image_tag}"
    docker push "${repository}/ui:latest"
    ;;
  push-api)
    authenticate_artifact_registry
    docker push "${repository}/api:${image_tag}"
    ;;
  push-kestra)
    authenticate_artifact_registry
    docker push "${repository}/kestra:${image_tag}"
    ;;
  push-ui)
    authenticate_artifact_registry
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
