local es = import '../common.libsonnet';

es.index('v1', {
  fdc_id: { type: 'long' },
  category: es.textKeyword(),
  brand_owner: es.textKeyword(),
  brand_name: es.textKeyword(),
  gtin_upc: { type: 'keyword' },
  ingredients: { type: 'text' },
  market_country: { type: 'keyword' },
  publication_date: {
    type: 'date',
    format: 'M/d/yyyy||strict_date_optional_time',
  },
  serving_size: { type: 'double' },
  serving_size_unit: { type: 'keyword' },
  nutrients: es.nutrients,
})
