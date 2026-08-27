{
  actions: [
    {
      add: {
        index: 'wikidata-food-entities-v1',
        alias: 'wikidata-food-entities',
        is_write_index: true,
      },
    },
    {
      add: {
        index: 'usda-foundation-foods-v1',
        alias: 'usda-foundation-foods',
        is_write_index: true,
      },
    },
    {
      add: {
        index: 'usda-branded-foods-v1',
        alias: 'usda-branded-foods',
        is_write_index: true,
      },
    },
    {
      add: {
        index: 'openfoodfacts-products-v1',
        alias: 'openfoodfacts-products',
        is_write_index: true,
      },
    },
  ] + [
    {
      add: {
        index: index,
        alias: 'food-entities',
      },
    }
    for index in [
      'wikidata-food-entities-v1',
      'usda-foundation-foods-v1',
      'usda-branded-foods-v1',
      'openfoodfacts-products-v1',
    ]
  ],
}
