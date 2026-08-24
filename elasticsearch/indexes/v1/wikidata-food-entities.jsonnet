local es = import '../common.libsonnet';

es.index('v1', {
  aliases: { type: 'keyword' },
  countries: es.relatedEntities,
  cuisines: es.relatedEntities,
  instance_of: es.relatedEntities,
  subclasses: es.relatedEntities,
  images: { type: 'keyword', index: false },
  articles: { type: 'keyword' },
})
