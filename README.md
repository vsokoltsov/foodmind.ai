# FoodMind AI

## Ingestion

Start Elasticsearch and apply the generated indexes before ingesting data:

```shell
docker compose up -d
uv run python cmd/ingestion.py --show-progress
```

The CLI starts Wikidata, USDA Foundation, USDA Branded, and Open Food Facts as
four concurrent source jobs. Wikidata retains its two-stage dlt normalization;
the archive readers stream records in bounded batches and all final writes use
the source-specific Elasticsearch repositories. Existing archives are reused.
Use `--force-download` only when they should be replaced.

The Elasticsearch bulk batch size defaults to 500 and can be changed with
`--batch-size`. Use `--wikidata-batch-size` separately for SPARQL query batches.

### Kestra orchestration

The Compose stack includes Kestra and PostgreSQL. Start the complete local
stack with:

```shell
docker compose up -d --build
```

Open Kestra at <http://localhost:8080>. The loopback-only `kestra-ui` proxy
automatically supplies the local Kestra credentials, so the UI does not show a
login prompt. Override the internal credentials with the
`KESTRA_BASIC_AUTH_USERNAME` and `KESTRA_BASIC_AUTH_PASSWORD` environment
variables; the proxy derives its authentication cookie from the same values.

The one-shot `kestra-init` service imports all version-controlled flows from
`infra/kestra/flows/` after Kestra is healthy. It is safe to rerun after editing
a flow:

```shell
docker compose run --rm kestra-init
```

Run `foodmind.foodmind_ingestion` in the UI to start the four source subflows
in parallel. Each source is visible as a separate execution, and its download,
transform/extract, dlt normalize, dlt staging load, Elasticsearch index, and
validation operations are separate Kestra tasks. Persistent dlt state lives in
the `kestra-dlt-data` volume, so independently scheduled tasks attach to the
same source-specific pipeline and DuckDB staging database. Each source flow
queues overlapping executions with a concurrency limit of one, while different
source flows continue running in parallel.

The Open Food Facts downloader keeps an interrupted transfer in a `.tmp` file,
retries transient HTTP failures, and resumes with an HTTP range request. Its
streaming read timeout is 15 minutes because the full export is roughly 12 GB;
connect, write, and connection-pool timeouts remain independently bounded.

The previous one-command ingestion remains available through
`cmd/ingestion.py`. The
stage interface used by Kestra can also be run directly, for example:

```shell
uv run python cmd/ingestion.py stage openfoodfacts normalize \
  --pipelines-dir .dlt/pipelines \
  --staging-dir .dlt/staging
```

## Elasticsearch index versions

Elasticsearch schemas are Jsonnet files under `elasticsearch/indexes/`. Each
physical index has its own definition, while `common.libsonnet` contains shared
mapping fragments. Jsonnet only renders native Elasticsearch request bodies;
all index operations use Elasticsearch REST APIs directly.

Start Elasticsearch and Kibana:

```shell
docker compose up -d
```

Compose mounts `elasticsearch/generated/v1/` read-only and runs
`infra/elasticsearch/init-indexes.sh` after Elasticsearch becomes healthy.
The one-shot `elasticsearch-init` service creates missing bootstrap indexes and
applies the initial aliases only when none exist. On later starts it preserves
the aliases' current snapshot targets and must finish successfully before
Kibana starts.

Inspect the initializer with:

```shell
docker compose logs elasticsearch-init
```

To initialize another generated version locally, provide its directory and
matching alias payload through the version variable:

```shell
ELASTICSEARCH_INDEX_VERSION=v2 docker compose up -d
```

Existing physical indexes are deliberately not modified. To rebuild the local
v1 indexes from scratch after changing their definitions, delete the local
Elasticsearch volume and start again. This removes all locally indexed data:

```shell
docker compose down --volumes
docker compose up -d
```

Install the Jsonnet CLI if necessary (`brew install jsonnet` on macOS), then
create the four physical indexes:

```shell
jsonnet elasticsearch/indexes/v1/wikidata-food-entities.jsonnet \
  | curl --fail --request PUT http://localhost:9200/wikidata-food-entities-v1 \
      --header 'Content-Type: application/json' --data-binary @-

jsonnet elasticsearch/indexes/v1/usda-foundation-foods.jsonnet \
  | curl --fail --request PUT http://localhost:9200/usda-foundation-foods-v1 \
      --header 'Content-Type: application/json' --data-binary @-

jsonnet elasticsearch/indexes/v1/usda-branded-foods.jsonnet \
  | curl --fail --request PUT http://localhost:9200/usda-branded-foods-v1 \
      --header 'Content-Type: application/json' --data-binary @-

jsonnet elasticsearch/indexes/v1/openfoodfacts-products.jsonnet \
  | curl --fail --request PUT http://localhost:9200/openfoodfacts-products-v1 \
      --header 'Content-Type: application/json' --data-binary @-
```

Activate all aliases with one atomic Elasticsearch request:

```shell
jsonnet elasticsearch/aliases/v1.jsonnet \
  | curl --fail --request POST http://localhost:9200/_aliases \
      --header 'Content-Type: application/json' --data-binary @-
```

The source-specific aliases are `wikidata-food-entities`,
`usda-foundation-foods`, `usda-branded-foods`, and `openfoodfacts-products`.
The `food-entities` read alias searches all four physical indexes.

Every staged ingestion writes into a new unaliased physical snapshot index.
The validation task compares that candidate with the dlt staging table and, on
success, atomically switches the source-specific alias and `food-entities`
alias. A failed validation leaves the currently published index untouched. Old
physical indexes are retained for explicit rollback or later retention cleanup.

For a schema change, copy the four definitions to an immutable `v2/`
directory, change their schema version, and create `-v2` physical indexes.
Populate them with the native `_reindex` API or rebuild from source data. A new
alias request should atomically remove the aliases from `-v1` and add them to
`-v2`. Rollback is the inverse alias request; the old physical indexes remain
untouched until their rollback window expires.
