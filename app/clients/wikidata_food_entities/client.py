"""Async client for retrieving food entity data from Wikidata."""

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
	"""Track and optionally display progress for a collection of query batches.

	Attributes:
		label: Human-readable name displayed with the progress indicator.
		total: Total number of batches to process.
		enabled: Whether progress should be printed to standard output.
		completed: Number of batches completed so far.
		started_at: Monotonic timestamp captured when tracking starts.
	"""

	label: str
	total: int
	enabled: bool
	completed: int = 0
	started_at: float = 0.0

	def __post_init__(self) -> None:
		"""Record the start time after initializing the dataclass."""
		# Monotonic time is unaffected by system clock corrections.
		self.started_at = time.monotonic()

	def mark_completed(self) -> None:
		"""Record one completed batch and refresh the progress output."""
		self.completed += 1
		if self.enabled:
			self.print()

	def finish(self) -> None:
		"""End the inline progress output with a newline when enabled."""
		if self.enabled:
			print()

	def print(self) -> None:
		"""Print the current completion percentage and estimated time remaining."""
		if self.total == 0:
			return
		# Estimate remaining time from the average duration of completed batches.
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
	"""Format a duration as a compact human-readable string.

	Args:
		seconds: Duration in seconds. Negative values are treated as zero.

	Returns:
		A duration formatted using seconds, minutes, or hours as appropriate.
	"""
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
	"""Retrieve food entities and related metadata from Wikidata.

	Attributes:
		client: Async HTTP client used to execute SPARQL requests.
		filename: Default output filename retained for ingestion configuration.
		url: Wikidata SPARQL endpoint URL.
		semaphore: Semaphore limiting concurrent batch requests.
		batch_size: Maximum number of Wikidata entity IDs per batch.
		concurrency: Maximum number of batches requested concurrently.
		max_retries: Maximum retry count after the initial request.
		retry_base_delay_seconds: Base duration used for exponential backoff.
	"""

	client: httpx.AsyncClient
	filename: str = "food_entities.json"
	url: str = "https://query.wikidata.org/sparql"
	semaphore: asyncio.Semaphore | None = None
	batch_size: int = 100
	concurrency: int = 1
	max_retries: int = 5
	retry_base_delay_seconds: float = 1.0

	def __post_init__(self) -> None:
		"""Validate client settings and initialize request concurrency control.

		Raises:
			ValueError: If batch, concurrency, or retry settings are invalid.
		"""
		if self.batch_size < 1:
			raise ValueError("batch_size must be at least 1")
		if self.concurrency < 1:
			raise ValueError("concurrency must be at least 1")
		if self.max_retries < 0:
			raise ValueError("max_retries must be at least 0")
		if self.retry_base_delay_seconds <= 0:
			raise ValueError("retry_base_delay_seconds must be greater than 0")

		# Share one semaphore across all batched requests made by this client.
		self.semaphore = asyncio.Semaphore(self.concurrency)

	async def get_entities(self) -> WikiDataResponse:
		"""Retrieve food entities from Wikidata.

		Returns:
			A validated response containing food entity bindings.

		Raises:
			httpx.HTTPError: If the endpoint request ultimately fails.
			RuntimeError: If Wikidata repeatedly returns invalid JSON.
		"""
		query = files(__package__).joinpath("sparql", "food_entities.sparql").read_text(
		encoding="utf-8"
		)
		payload = await self._run_query(query)
		results = WikiDataResponse.model_validate(payload)
		return results

	async def get_aliases(
		self, qids: list[str], *, show_progress: bool = False
	) -> WikiDataAliasResponse:
		"""Retrieve English aliases for Wikidata entities.

		Args:
			qids: Entity identifiers formatted for SPARQL, such as ``wd:Q123``.
			show_progress: Whether to print batch progress and an ETA.

		Returns:
			A validated response containing alias bindings from all batches.

		Raises:
			httpx.HTTPError: If an endpoint request ultimately fails.
			RuntimeError: If Wikidata repeatedly returns invalid JSON.
		"""
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
		"""Retrieve instance and subclass relationships for Wikidata entities.

		Args:
			qids: Entity identifiers formatted for SPARQL, such as ``wd:Q123``.
			show_progress: Whether to print batch progress and an ETA.

		Returns:
			A validated response containing taxonomy bindings from all batches.

		Raises:
			httpx.HTTPError: If an endpoint request ultimately fails.
			RuntimeError: If Wikidata repeatedly returns invalid JSON.
		"""
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
		"""Retrieve countries of origin and cuisines for Wikidata entities.

		Args:
			qids: Entity identifiers formatted for SPARQL, such as ``wd:Q123``.
			show_progress: Whether to print batch progress and an ETA.

		Returns:
			A validated response containing origin and cuisine bindings.

		Raises:
			httpx.HTTPError: If an endpoint request ultimately fails.
			RuntimeError: If Wikidata repeatedly returns invalid JSON.
		"""
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
		"""Retrieve image and English Wikipedia article links for entities.

		Args:
			qids: Entity identifiers formatted for SPARQL, such as ``wd:Q123``.
			show_progress: Whether to print batch progress and an ETA.

		Returns:
			A validated response containing media and article bindings.

		Raises:
			httpx.HTTPError: If an endpoint request ultimately fails.
			RuntimeError: If Wikidata repeatedly returns invalid JSON.
		"""
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
		"""Execute a parameterized SPARQL query in concurrent batches.

		Args:
			query_template: SPARQL template containing an ``$items`` placeholder.
			values: Values inserted into the template and divided into batches.
			progress_label: Label displayed by the progress indicator.
			show_progress: Whether progress should be printed.

		Returns:
			A list containing the raw result bindings for each batch.
		"""
		batches = list(self._batches(values))
		progress = BatchProgress(
			label=progress_label,
			total=len(batches),
			enabled=show_progress,
		)
		# Preserve input batch ordering while allowing bounded concurrent requests.
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
		"""Execute one batch after substituting its entity identifiers.

		Args:
			query_template: SPARQL template containing an ``$items`` placeholder.
			batch: Entity identifiers to insert into the query.
			progress: Shared progress tracker updated after a successful request.

		Returns:
			Raw result bindings returned for the batch.

		Raises:
			RuntimeError: If the client semaphore has not been initialized.
		"""
		if self.semaphore is None:
			raise RuntimeError("Client semaphore is not initialized")
		# Hold the semaphore for the complete request and response parsing cycle.
		async with self.semaphore:
			query = query_template.replace("$items", "\n".join(batch))
			payload = await self._run_query(query)
			progress.mark_completed()
			return payload["results"]["bindings"]

	async def _run_query(self, query: str):
		"""Execute a SPARQL query and decode its JSON response with retries.

		Args:
			query: Complete SPARQL query to execute.

		Returns:
			The decoded JSON response.

		Raises:
			httpx.HTTPError: If the endpoint request ultimately fails.
			RuntimeError: If every response contains invalid JSON.
		"""
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
				# Invalid JSON can be transient when the endpoint is under load.
				await asyncio.sleep(self._retry_delay(attempt))

		preview = last_response.text[:500] if last_response is not None else ""
		response_length = len(last_response.content) if last_response is not None else 0
		raise RuntimeError(
		f"Wikidata returned invalid JSON after retries: {last_error}. "
		f"Response length={response_length} preview={preview!r}"
		) from last_error

	async def _post_with_retries(self, query: str) -> httpx.Response:
		"""Post a SPARQL query, retrying transient HTTP and network failures.

		Args:
			query: Complete SPARQL query to submit.

		Returns:
			A successful HTTP response.

		Raises:
			httpx.HTTPStatusError: If a non-retryable status is returned or all
				retries are exhausted.
			httpx.RequestError: If all retries fail because of transport errors.
		"""
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
		"""Calculate the delay before retrying a failed request.

		Args:
			attempt: Zero-based retry attempt number.
			response: Optional response that may define a ``Retry-After`` header.

		Returns:
			The number of seconds to wait before the next attempt.
		"""
		retry_after = None
		if response is not None:
			retry_after = response.headers.get("Retry-After")
		if retry_after is not None:
			try:
				# Respect server throttling guidance when it is expressed in seconds.
				return float(retry_after)
			except ValueError:
				pass
		return self.retry_base_delay_seconds * (2 ** attempt)

	def _batches(self, values: list[str]):
		"""Yield consecutive groups of values limited by ``batch_size``.

		Args:
			values: Values to divide into batches.

		Yields:
			The next list of at most ``batch_size`` values.
		"""
		for index in range(0, len(values), self.batch_size):
			yield values[index:index + self.batch_size]
