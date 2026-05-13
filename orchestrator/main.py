"""Entry point for the Smart Home Agent Orchestrator.

Demonstrates how to use ``AgentOrchestrator`` to dispatch tasks to the
Go-based Lighting Agent and collect results.

Usage::

    # From the project root, with NATS running:
    python -m orchestrator.main

    # Or with a custom NATS URL:
    set NATS_URL=nats://localhost:4222
    python -m orchestrator.main
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

from orchestrator.core import AgentOrchestrator

# Load environment variables from .env (if present).
load_dotenv()

# ── Logging configuration ────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
logger = logging.getLogger("orchestrator.main")


# ── Demo scenarios ───────────────────────────────────────────────────────────

#: Payload for scenario 1 — normal turn-on (ambient light is adequate).
SCENARIO_TURN_ON = {
    "device_id": "light_01",
    "state": "on",
    "brightness": 80,
    "ambient_light": 500,
}

#: Payload for scenario 2 — auto-trigger (ambient light < 200 lux, so the
#: Lighting Agent will override ``state`` to ``"on"`` regardless).
SCENARIO_AUTO_TRIGGER = {
    "device_id": "light_01",
    "state": "off",
    "brightness": 0,
    "ambient_light": 100,
}

#: Payload for scenario 3 — invalid command type (the agent will reject it).
SCENARIO_INVALID_TYPE = {
    "device_id": "light_01",
    "state": "on",
    "brightness": 50,
    "ambient_light": 300,
}


async def run_scenario(
    orchestrator: AgentOrchestrator,
    name: str,
    payload: dict,
    task_type: str = "set_state",
    timeout: float = 10.0,
) -> None:
    """Run a single demonstration scenario and print the result."""
    print(f"\n{'='*60}")
    print(f"  Scenario: {name}")
    print(f"{'='*60}")

    try:
        result = await orchestrator.send_task(
            subject="tasks.lighting",
            payload=payload,
            task_type=task_type,
            timeout=timeout,
        )
        print(f"  [OK] Success")
        print(f"  Result:")
        for key, value in result.items():
            print(f"    {key}: {value}")
    except TimeoutError:
        print(f"  [TIMEOUT] — Is the Go Lighting Agent running?")
    except ConnectionError as exc:
        print(f"  [ERROR] Connection error: {exc}")
    except Exception as exc:
        print(f"  [ERROR] Unexpected error: {exc}")


async def main() -> None:
    """Main entry point — connects the orchestrator and runs scenarios."""
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")

    orchestrator = AgentOrchestrator(nats_url=nats_url)

    try:
        await orchestrator.connect()
    except ConnectionError as exc:
        logger.error("Failed to connect to NATS at %s: %s", nats_url, exc)
        sys.exit(1)

    print("\n" + "="*60)
    print(f"  Smart Home Multi-Agent System — Orchestrator Demo")
    print("="*60)
    print(f"  NATS URL:     {nats_url}")
    print(f"  Agent target: tasks.lighting")
    print(f"  Result topic: tasks.completed")

    try:
        # Scenario 1 — Normal turn-on.
        await run_scenario(
            orchestrator,
            "1 — Normal Turn On",
            SCENARIO_TURN_ON,
        )

        # Scenario 2 — Auto-trigger (ambient light below 200 lux).
        await run_scenario(
            orchestrator,
            "2 — Auto-Trigger (darkness)",
            SCENARIO_AUTO_TRIGGER,
        )

        # Scenario 3 — Invalid command type (expect the agent to reject it).
        await run_scenario(
            orchestrator,
            "3 — Invalid Task Type",
            SCENARIO_INVALID_TYPE,
            task_type="invalid_type",
        )

        # Scenario 4 — Timeout demonstration (no agent listening on this subject).
        await run_scenario(
            orchestrator,
            "4 — Timeout (no agent listening)",
            SCENARIO_TURN_ON,
            timeout=3.0,
        )

    finally:
        await orchestrator.close()

    print(f"\n{'='*60}")
    print("  Demo complete.")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
