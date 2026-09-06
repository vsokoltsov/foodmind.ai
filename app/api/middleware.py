"""FastAPI application and middleware configuration."""

from collections.abc import Awaitable, Callable
from time import perf_counter

from fastapi import FastAPI, Request
from prometheus_client import make_asgi_app
from starlette.responses import Response

from app.api.endpoints import router
from app.api.lifespan import lifespan
from app.observability import metrics
from app.observability.tracing import tracing

app = FastAPI(
    title="FoodMind API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
app.mount("/metrics", make_asgi_app())
tracing.configure(app)


@app.middleware("http")
async def instrument_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Measure API request rates and latency without high-cardinality labels."""
    if request.url.path == "/metrics":
        return await call_next(request)

    method = request.method
    metrics.api_requests_in_progress.labels(method=method).inc()
    started = perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or "/unmatched"
        duration = perf_counter() - started
        metrics.api_requests_in_progress.labels(method=method).dec()
        metrics.record_api_request(
            method=method,
            path=route_path,
            status=status_code,
            duration_seconds=duration,
        )
