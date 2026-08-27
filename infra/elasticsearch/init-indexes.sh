#!/usr/bin/env bash

set -euo pipefail

readonly ELASTICSEARCH_URL="${ELASTICSEARCH_URL:-http://elasticsearch:9200}"
readonly INDEX_DEFINITIONS_DIR="${INDEX_DEFINITIONS_DIR:-/indexes}"
readonly INDEX_VERSION="${ELASTICSEARCH_INDEX_VERSION:-v1}"

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

curl \
  --silent \
  --show-error \
  --fail \
  --request POST \
  "${ELASTICSEARCH_URL}/_aliases" \
  --header 'Content-Type: application/json' \
  --data-binary "@${ALIASES_FILE}"

echo
echo "Applied aliases for Elasticsearch index version ${INDEX_VERSION}"
