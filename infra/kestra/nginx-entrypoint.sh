#!/bin/sh

set -eu

KESTRA_BASIC_AUTH_COOKIE="$(
  printf '%s:%s' \
    "${KESTRA_BASIC_AUTH_USERNAME}" \
    "${KESTRA_BASIC_AUTH_PASSWORD}" \
    | base64 \
    | tr -d '\n'
)"
export KESTRA_BASIC_AUTH_COOKIE

exec /docker-entrypoint.sh nginx -g 'daemon off;'
