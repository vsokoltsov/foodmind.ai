local textKeyword(ignoreAbove=512) = {
  type: 'text',
  fields: {
    keyword: {
      type: 'keyword',
      ignore_above: ignoreAbove,
    },
  },
};

local commonProperties = {
  id: { type: 'keyword' },
  source: { type: 'keyword' },
  entity_type: { type: 'keyword' },
  label: textKeyword(),
  description: { type: 'text' },
};

local relatedEntities = {
  type: 'nested',
  properties: {
    id: { type: 'keyword' },
    label: textKeyword(),
  },
};

local nutrients = {
  type: 'nested',
  properties: {
    id: { type: 'long' },
    number: { type: 'keyword' },
    name: textKeyword(),
    unit: { type: 'keyword' },
    amount: { type: 'double' },
  },
};

{
  textKeyword:: textKeyword,
  relatedEntities:: relatedEntities,
  nutrients:: nutrients,

  index(version, extraProperties): {
    settings: {
      number_of_shards: 1,
      number_of_replicas: 0,
      refresh_interval: '30s',
    },
    mappings: {
      dynamic: 'strict',
      _meta: {
        schema_version: version,
      },
      properties: commonProperties + extraProperties,
    },
  },
}
