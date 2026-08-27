local es = import '../common.libsonnet';

es.index('v1', {
  code: { type: 'keyword' },
  brands: es.textKeyword(),
  brands_tags: { type: 'keyword' },
  categories: { type: 'text' },
  categories_tags: { type: 'keyword' },
  countries: { type: 'text' },
  countries_tags: { type: 'keyword' },
  ingredients: { type: 'text' },
  ingredients_tags: { type: 'keyword' },
  allergens: { type: 'text' },
  allergens_tags: { type: 'keyword' },
  traces: { type: 'text' },
  traces_tags: { type: 'keyword' },
  labels_tags: { type: 'keyword' },
  quantity: { type: 'keyword' },
  serving_size: { type: 'keyword' },
  nutrition_grade: { type: 'keyword' },
  nova_group: { type: 'byte' },
  nutriments: { type: 'flattened' },
  image_url: { type: 'keyword', index: false },
  image_front_url: { type: 'keyword', index: false },
  last_modified_at: {
    type: 'date',
    format: 'epoch_second',
  },
})
