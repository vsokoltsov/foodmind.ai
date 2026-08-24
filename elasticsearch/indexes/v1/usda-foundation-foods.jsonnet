local es = import '../common.libsonnet';

es.index('v1', {
  fdc_id: { type: 'long' },
  category: es.textKeyword(),
  scientific_name: es.textKeyword(),
  publication_date: {
    type: 'date',
    format: 'M/d/yyyy||strict_date_optional_time',
  },
  nutrients: es.nutrients,
})
