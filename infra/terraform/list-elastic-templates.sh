#!/usr/bin/env bash
# List non-deprecated Elastic Cloud Hosted deployment templates for one region.
#
# Usage:
#   EC_API_KEY='...' infra/terraform/list-elastic-templates.sh gcp-europe-west3
set -euo pipefail

region="${1:?Pass an Elastic Cloud region, for example gcp-europe-west3.}"
api_key="${EC_API_KEY:?Set EC_API_KEY to an Elastic Cloud control-plane API key.}"

curl --fail-with-body --silent --show-error \
  --header "Authorization: ApiKey ${api_key}" \
  "https://api.elastic-cloud.com/api/v1/deployments/templates?region=${region}&hide_deprecated=true" \
  | jq -r '
      if type == "array" then .[]
      elif .templates? then .templates[]
      else error("Elastic Cloud returned an unexpected deployment-template response")
      end
      | [.id, .name] | @tsv
    '
