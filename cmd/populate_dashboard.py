"""Populate the local Prometheus/Grafana dashboard with representative traffic.

The script deliberately uses the public streaming API instead of importing the
metrics singleton. This exercises the same API, NATS, worker, orchestrator,
repository, and feedback paths used by the UI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import httpx


@dataclass(frozen=True)
class SeedPrompt:
    """One successful request used to exercise a router path."""

    label: str
    prompt: str


PROMPTS = (
    SeedPrompt("food search", "Find Mediterranean chickpea foods."),
    SeedPrompt(
        "nutrition analysis",
        "How much protein and fiber do chickpeas contain?",
    ),
    SeedPrompt(
        "recommendation",
        "Recommend high-protein vegetarian foods without peanuts under 300 calories.",
    ),
    SeedPrompt("product comparison", "Compare hummus and chickpea pasta."),
    SeedPrompt(
        "planned workflow",
        "I have chickpeas, lentils, and hummus. Help me choose the best option for dinner.",
    ),
)


async def stream_chat(
    client: httpx.AsyncClient,
    *,
    user_id: UUID,
    prompt: str,
) -> dict[str, Any]:
    """Submit one message and wait for its completed worker result."""
    answer: dict[str, Any] | None = None
    event = "message"
    async with client.stream(
        "POST",
        "/chats/stream",
        json={"user_id": str(user_id), "message": prompt},
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "error":
                    raise RuntimeError(str(data.get("message", "Chat failed")))
                if event == "completed":
                    answer = dict(data)
    if answer is None:
        raise RuntimeError("The API stream completed without an answer")
    return answer


async def seed(api_url: str, timeout_seconds: float) -> None:
    """Generate successful API, worker, LLM, retrieval, and feedback metrics."""
    user_id = uuid4()
    timeout = httpx.Timeout(
        connect=10.0,
        read=timeout_seconds,
        write=30.0,
        pool=30.0,
    )
    async with httpx.AsyncClient(base_url=api_url, timeout=timeout) as client:
        response = await client.get("/health")
        response.raise_for_status()
        print(f"Healthy API: {api_url}")

        for index, item in enumerate(PROMPTS, start=1):
            print(f"[{index}/{len(PROMPTS)}] {item.label}: {item.prompt}")
            result = await stream_chat(client, user_id=user_id, prompt=item.prompt)
            chat_id = UUID(str(result["chat_id"]))
            message_id = str(result["message_id"])

            # Exercise read endpoints as well as the write/stream path.
            chats = await client.get("/chats", params={"user_id": str(user_id)})
            chats.raise_for_status()
            messages = await client.get(
                f"/chats/{chat_id}/messages", params={"user_id": str(user_id)}
            )
            messages.raise_for_status()

            feedback = await client.put(
                f"/chats/{chat_id}/messages/{message_id}/feedback",
                json={"user_id": str(user_id), "is_useful": index % 2 == 1},
            )
            feedback.raise_for_status()
            print(
                f"  completed chat={chat_id} agents={result.get('used_agents', [])} "
                f"feedback={index % 2 == 1}"
            )

    print(f"Seeded {len(PROMPTS)} successful chat turns for user {user_id}.")


def parse_args() -> argparse.Namespace:
    """Parse command-line options for the local dashboard seeder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="FoodMind API base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="Maximum seconds to wait for each worker result (default: %(default)s)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    asyncio.run(seed(arguments.api_url.rstrip("/"), arguments.timeout))
