import asyncio
from dataclasses import dataclass
import json
import time
import httpx
from app.clients.models import USER_AGENT
from app.clients.wikidata_food_entities.models import (
	WikiDataAliasResponse,
	WikiDataResponse,
	WikidataAliasResults,
	WikidataMediaArticleResults,
	WikidataMediaArticlesResponse,
	WikidataOriginalCuisineResponse,
	WikidataOriginalCuisineResults,
	WikidataTaxonomyResponse,
	WikidataTaxonomyResults,
)
from importlib.resources import files

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

@dataclass
class BatchProgress:
	label: str
	total: int
	enabled: bool
	completed: int = 0
	started_at: float = 0.0

	def __post_init__(self) -> None:
		self.started_at = time.monotonic()

	def mark_completed(self) -> None:
		self.completed += 1
		if self.enabled:
			self.print()

	def finish(self) -> None:
		if self.enabled:
			print()

	def print(self) -> None:
		if self.total == 0:
			return
		elapsed_seconds = time.monotonic() - self.started_at
		average_batch_seconds = elapsed_seconds / self.completed
		remaining_batches = self.total - self.completed
		remaining_seconds = remaining_batches * average_batch_seconds
		percent = self.completed / self.total * 100
		print(
			"\r"
			f"{self.label}: {self.completed}/{self.total} batches "
			f"({percent:5.1f}%) | "
			f"elapsed {format_duration(elapsed_seconds)} | "
			f"eta {format_duration(remaining_seconds)}",
			end="",
			flush=True,
		)


def format_duration(seconds: float) -> str:
	seconds = max(0, int(seconds))
	minutes, seconds = divmod(seconds, 60)
	hours, minutes = divmod(minutes, 60)
	if hours:
		return f"{hours}h {minutes:02d}m {seconds:02d}s"
	if minutes:
		return f"{minutes}m {seconds:02d}s"
	return f"{seconds}s"

@dataclass
class WikidataFoodEntitiesClient:
	client: httpx.AsyncClient
	filename: str = "food_entities.json"
	url: str = "https://query.wikidata.org/sparql"
	semaphore: asyncio.Semaphore | None = None
	batch_size: int = 100
	concurrency: int = 1
	max_retries: int = 5
	retry_base_delay_seconds: float = 1.0

	def __post_init__(self) -> None:
		if self.batch_size < 1:
			raise ValueError("batch_size must be at least 1")
		if self.concurrency < 1:
			raise ValueError("concurrency must be at least 1")
		self.semaphore = asyncio.Semaphore(self.concurrency)

		if self.max_retries < 0:
			raise ValueError("max_retries must be at least 0")
		if self.retry_base_delay_seconds <= 0:
			raise ValueError("retry_base_delay_seconds must be greater than 0")

	

	async def get_entities(self) -> WikiDataResponse:
		query = files(__package__).joinpath("sparql", "food_entities.sparql").read_text(
		encoding="utf-8"
		)
		payload = await self._run_query(query)
		results = WikiDataResponse.model_validate(payload)
		return results

	async def get_aliases(
		self, qids: list[str], *, show_progress: bool = False
	) -> WikiDataAliasResponse:
		query_template = files(__package__).joinpath("sparql", "aliases.sparql").read_text(
			encoding="utf-8"
		)
		batch_results = await self._run_batched_query(
			query_template=query_template,
			values=qids,
			progress_label="Aliases",
			show_progress=show_progress,
		)
		bindings = [
			binding
			for batch in batch_results
			for binding in batch
		]
		results = WikidataAliasResults.model_validate(
			obj={"bindings": bindings}
		)
		return WikiDataAliasResponse(
			results=results
		)
	async def get_taxonomy(
		self, qids: list[str], *, show_progress: bool = False
	) -> WikidataTaxonomyResponse:
		query_template = files(__package__).joinpath("sparql", "taxonomy.sparql").read_text(
			encoding="utf-8"
		)
		batch_results = await self._run_batched_query(
			query_template=query_template,
			values=qids,
			progress_label="Taxonomy",
			show_progress=show_progress,
		)
		bindings = [
			binding
			for batch in batch_results
			for binding in batch
		]
		results = WikidataTaxonomyResults.model_validate({"bindings": bindings})
		return WikidataTaxonomyResponse(results=results)

	async def get_original_cousine(
		self, qids: list[str], *, show_progress: bool = False
	) -> WikidataOriginalCuisineResponse:
		query_template = files(__package__).joinpath(
			"sparql", "original_cusine.sparql"
		).read_text(
			encoding="utf-8"
		)
		batch_results = await self._run_batched_query(
			query_template=query_template,
			values=qids,
			progress_label="Original cusine",
			show_progress=show_progress,
		)
		bindings = [
			binding
			for batch in batch_results
			for binding in batch
		]
		results = WikidataOriginalCuisineResults.model_validate(
			{"bindings": bindings}
		)
		return WikidataOriginalCuisineResponse(results=results)

	async def get_media_articles(
		self, qids: list[str], *, show_progress: bool = False
	) -> WikidataMediaArticlesResponse:
		query_template = files(__package__).joinpath(
			"sparql", "media_articles.sparql"
		).read_text(
			encoding="utf-8"
		)
		batch_results = await self._run_batched_query(
			query_template=query_template,
			values=qids,
			progress_label="Original cusine",
			show_progress=show_progress,
		)
		bindings = [
			binding
			for batch in batch_results
			for binding in batch
		]
		results = WikidataMediaArticleResults.model_validate({"bindings": bindings})
		return WikidataMediaArticlesResponse(results=results)

	async def _run_batched_query(
		self,
		*,
		query_template: str,
		values: list[str],
		progress_label: str,
		show_progress: bool,
	) -> list[list[dict]]:
		batches = list(self._batches(values))
		progress = BatchProgress(
			label=progress_label,
			total=len(batches),
			enabled=show_progress,
		)
		batch_results = await asyncio.gather(
			*(
				self._fetch_batch(
					query_template=query_template,
					batch=batch,
					progress=progress,
				)
				for batch in batches
			)
		)
		progress.finish()
		return batch_results

	async def _fetch_batch(
		self,
		*,
		query_template: str,
		batch: list[str],
		progress: "BatchProgress",
	) -> list[dict]:
		if self.semaphore is None:
			raise RuntimeError("Client semaphore is not initialized")
		async with self.semaphore:
			query = query_template.replace("$items", "\n".join(batch))
			payload = await self._run_query(query)
			progress.mark_completed()
			return payload["results"]["bindings"]

	async def _run_query(self, query: str):
		last_error: json.JSONDecodeError | None = None
		last_response: httpx.Response | None = None
		for attempt in range(self.max_retries + 1):
			response = await self._post_with_retries(query)
			try:
				return response.json()
			except json.JSONDecodeError as exc:
				last_error = exc
				last_response = response
				if attempt == self.max_retries:
					break
				await asyncio.sleep(self._retry_delay(attempt))

		preview = last_response.text[:500] if last_response is not None else ""
		response_length = len(last_response.content) if last_response is not None else 0
		raise RuntimeError(
		f"Wikidata returned invalid JSON after retries: {last_error}. "
		f"Response length={response_length} preview={preview!r}"
		) from last_error

	async def _post_with_retries(self, query: str) -> httpx.Response:
		last_error: httpx.HTTPStatusError | httpx.RequestError | None = None
		for attempt in range(self.max_retries + 1):
			try:
				response = await self.client.post(
					self.url,
					data={"query": query, "format": "json"},
					headers={
						"Accept": "application/sparql-results+json",
						"User-Agent": USER_AGENT,
					},
				)
				response.raise_for_status()
				return response
			except httpx.HTTPStatusError as exc:
				last_error = exc
				if exc.response.status_code not in RETRYABLE_STATUS_CODES:
					raise
				if attempt == self.max_retries:
					raise
				await asyncio.sleep(self._retry_delay(attempt, exc.response))
			except httpx.RequestError as exc:
				last_error = exc
				if attempt == self.max_retries:
					raise
				await asyncio.sleep(self._retry_delay(attempt))

		raise RuntimeError("Wikidata query failed after retries") from last_error

	def _retry_delay(
	  self, attempt: int, response: httpx.Response | None = None
	) -> float:
		retry_after = None
		if response is not None:
			retry_after = response.headers.get("Retry-After")
		if retry_after is not None:
			try:
				return float(retry_after)
			except ValueError:
				pass
		return self.retry_base_delay_seconds * (2 ** attempt)

	def _batches(self, values: list[str]):
		for index in range(0, len(values), self.batch_size):
			yield values[index:index + self.batch_size]
