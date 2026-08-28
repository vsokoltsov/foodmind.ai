import asyncio

from elasticsearch import AsyncElasticsearch


async def get_document(
    elasticsearch_url: str,
    *,
    index: str,
    document_id: str,
) -> dict:
    """Refresh an index and retrieve one complete stored document."""
    async with AsyncElasticsearch(elasticsearch_url) as client:
        await client.indices.refresh(index=index)
        response = await client.get(index=index, id=document_id)
        return dict(response)


def run(coroutine):
    """Run one complete async repository scenario on a single event loop."""
    return asyncio.run(coroutine)
