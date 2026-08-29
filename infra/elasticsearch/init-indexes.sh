#!/usr/bin/env bash

set -euo pipefail

readonly ELASTICSEARCH_URL="${ELASTICSEARCH_URL:-http://elasticsearch:9200}"
readonly INDEX_DEFINITIONS_DIR="${INDEX_DEFINITIONS_DIR:-/indexes}"
readonly INDEX_VERSION="${ELASTICSEARCH_INDEX_VERSION:-v1}"
readonly MAX_READY_ATTEMPTS="${ELASTICSEARCH_INIT_MAX_READY_ATTEMPTS:-30}"
readonly READY_RETRY_DELAY_SECONDS="${ELASTICSEARCH_INIT_RETRY_DELAY_SECONDS:-2}"

wait_for_elasticsearch() {
  local attempt

  for ((attempt = 1; attempt <= MAX_READY_ATTEMPTS; attempt += 1)); do
    if curl \
      --silent \
      --show-error \
      --fail \
      --output /dev/null \
      "${ELASTICSEARCH_URL}/_cluster/health?wait_for_status=yellow&timeout=5s"; then
      echo "Elasticsearch is ready"
      return 0
    fi

    if ((attempt < MAX_READY_ATTEMPTS)); then
      echo \
        "Waiting for Elasticsearch (${attempt}/${MAX_READY_ATTEMPTS})..." \
        >&2
      sleep "${READY_RETRY_DELAY_SECONDS}"
    fi
  done

  echo \
    "Elasticsearch did not become ready after ${MAX_READY_ATTEMPTS} attempts" \
    >&2
  return 1
}

create_index_if_missing() {
  local index_name="$1"
  local definition_file="$2"
  local status

  if [[ ! -r "${definition_file}" ]]; then
    echo "Index definition is not readable: ${definition_file}" >&2
    return 1
  fi

  status="$(
    curl \
      --silent \
      --show-error \
      --retry 5 \
      --retry-connrefused \
      --retry-delay 1 \
      --output /dev/null \
      --write-out '%{http_code}' \
      --head \
      "${ELASTICSEARCH_URL}/${index_name}"
  )"

  case "${status}" in
    200)
      echo "Index already exists: ${index_name}"
      ;;
    404)
      curl \
        --silent \
        --show-error \
        --fail \
        --retry 5 \
        --retry-connrefused \
        --retry-delay 1 \
        --request PUT \
        "${ELASTICSEARCH_URL}/${index_name}" \
        --header 'Content-Type: application/json' \
        --data-binary "@${definition_file}"
      echo
      echo "Created index: ${index_name}"
      ;;
    *)
      echo \
        "Unexpected HTTP ${status} while checking index ${index_name}" \
        >&2
      return 1
      ;;
  esac
}

wait_for_elasticsearch

create_index_if_missing \
  "wikidata-food-entities-${INDEX_VERSION}" \
  "${INDEX_DEFINITIONS_DIR}/wikidata-food-entities.json"

create_index_if_missing \
  "usda-foundation-foods-${INDEX_VERSION}" \
  "${INDEX_DEFINITIONS_DIR}/usda-foundation-foods.json"

create_index_if_missing \
  "usda-branded-foods-${INDEX_VERSION}" \
  "${INDEX_DEFINITIONS_DIR}/usda-branded-foods.json"

create_index_if_missing \
  "openfoodfacts-products-${INDEX_VERSION}" \
  "${INDEX_DEFINITIONS_DIR}/openfoodfacts-products.json"

readonly ALIASES_FILE="${INDEX_DEFINITIONS_DIR}/aliases.json"
if [[ ! -r "${ALIASES_FILE}" ]]; then
  echo "Alias definition is not readable: ${ALIASES_FILE}" >&2
  exit 1
fi

source_alias_count=0
for alias in \
  wikidata-food-entities \
  usda-foundation-foods \
  usda-branded-foods \
  openfoodfacts-products; do
  if curl \
    --silent \
    --show-error \
    --output /dev/null \
    --head \
    --fail \
    "${ELASTICSEARCH_URL}/_alias/${alias}"; then
    source_alias_count=$((source_alias_count + 1))
  fi
done

case "${source_alias_count}" in
  0)
    curl \
      --silent \
      --show-error \
      --fail \
      --retry 5 \
      --retry-connrefused \
      --retry-delay 1 \
      --request POST \
      "${ELASTICSEARCH_URL}/_aliases" \
      --header 'Content-Type: application/json' \
      --data-binary "@${ALIASES_FILE}"
    echo
    echo "Applied initial aliases for Elasticsearch index version ${INDEX_VERSION}"
    ;;
  4)
    echo "Source aliases already exist; preserving their current snapshot targets"
    ;;
  *)
    echo \
      "Only ${source_alias_count}/4 source aliases exist; refusing a partial bootstrap" \
      >&2
    exit 1
    ;;
esac
