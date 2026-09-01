"""Interactive command-line entry point for the FoodMind agent."""

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.foodmind import ask_foodmind


def main() -> None:
    """Run the agent once for a prompt supplied on the command line."""
    parser = argparse.ArgumentParser(description="Ask the FoodMind AI agent.")
    parser.add_argument("prompt", help="Question or instruction for the agent")
    args = parser.parse_args()
    print(asyncio.run(ask_foodmind(args.prompt)))


if __name__ == "__main__":
    main()
