"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.endpoints import router
from app.api.lifespan import lifespan

app = FastAPI(
    title="FoodMind API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
