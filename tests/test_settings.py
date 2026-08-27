from collections.abc import Iterator

import pytest

from app.settings import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Isolate the cached settings instance between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_settings_uses_default_elasticsearch_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ELASTICSEARCH_URL", raising=False)

    settings = get_settings()

    assert settings.ELASTICSEARCH_URL == "http://localhost:9200"


def test_get_settings_reads_environment_and_caches_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://elasticsearch.test:9200")

    first = get_settings()
    second = get_settings()

    assert first.ELASTICSEARCH_URL == "http://elasticsearch.test:9200"
    assert second is first
