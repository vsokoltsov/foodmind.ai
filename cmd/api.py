"""Development command for running the FoodMind HTTP API."""

import sys
from pathlib import Path

import uvicorn

# Running this file directly puts ``cmd/`` rather than the repository root on
# sys.path. Add the root so the application package remains importable.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    """Start the API server with source-code reload enabled for development."""
    uvicorn.run(
        "app.api.middleware:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(PROJECT_ROOT / "app")],
    )


if __name__ == "__main__":
    main()
