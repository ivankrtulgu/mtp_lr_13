"""Core orchestrator — the central coordinator of the Smart Home Multi-Agent System.

``AgentOrchestrator`` communicates with autonomous agent microservices over
NATS using an asynchronous request-response pattern.  It publishes tasks to
agent-specific subjects (e.g. ``tasks.lighting``) and correlates the
asynchronous replies (published to ``tasks.completed``) via ``asyncio.Future``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Final
from uuid import uuid4

import nats
from nats.aio.msg import Msg as NatsMsg

from orchestrator.models import ResultModel, TaskModel

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrator that dispatches tasks to agents and correlates results.

    Typical usage::

        orchestrator = AgentOrchestrator()
        await orchestrator.connect()

        result = await orchestrator.send_task(
            subject="tasks.lighting",
            payload={"device_id": "light_01", "state": "on", ...},
        )

        await orchestrator.close()

    Attributes:
        nc: The underlying NATS client connection (``None`` until connected).
    """

    # ── NATS subject constants ──────────────────────────────────────────

    DEFAULT_RESULT_SUBJECT: Final[str] = "tasks.completed"

    # ── Lifecycle ───────────────────────────────────────────────────────

    def __init__(self, nats_url: str = "nats://localhost:4222") -> None:
        self._nats_url = nats_url
        self.nc: nats.NATS | None = None

        # Mapping: task_id -> asyncio.Future[dict]
        # Used to correlate an incoming result on tasks.completed with the
        # original send_task() call that is awaiting a response.
        self._pending: dict[str, Any] = {}  # asyncio.Future

        # Subscription handle so we can unsubscribe on shutdown.
        self._sub: Any = None

        # Task counter — incremented on every send_task() call.
        self._task_count: int = 0

    async def connect(self) -> None:
        """Establish a NATS connection and subscribe to result replies.

        Raises:
            nats.errors.ConnectionFailed: If the NATS server is unreachable.
        """
        logger.info("Connecting to NATS at %s ...", self._nats_url)
        self.nc = await nats.connect(
            self._nats_url,
            name="agent-orchestrator",
            reconnect_time_wait=2,
            max_reconnect_attempts=10,
        )
        logger.info("Connected to NATS (URL: %s)", self._nats_url)

        # Subscribe to the result subject and wire up the handler.
        self._sub = await self.nc.subscribe(
            self.DEFAULT_RESULT_SUBJECT,
            cb=self._on_result,
        )
        logger.info(
            "Subscribed to '%s' — awaiting agent results",
            self.DEFAULT_RESULT_SUBJECT,
        )

    async def close(self) -> None:
        """Gracefully shut down the NATS connection.

        * Unsubscribes from the result subject.
        * Drains the connection (flushes pending messages).
        * Closes the connection.
        * Cancels all pending futures so waiting callers don't hang.
        """
        logger.info("Shutting down orchestrator ...")

        # Cancel all outstanding futures so awaiting tasks don't hang.
        for task_id, fut in self._pending.items():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

        if self.nc is not None:
            if self._sub is not None:
                try:
                    await self._sub.unsubscribe()
                except Exception:
                    logger.debug("Error unsubscribing (ignored)", exc_info=True)
            try:
                await self.nc.drain()
            except Exception:
                logger.debug("Error draining NATS connection (ignored)", exc_info=True)
            self.nc = None

        logger.info("Orchestrator shut down complete.")

    # ── Core API ────────────────────────────────────────────────────────

    async def send_task(
        self,
        subject: str,
        payload: dict[str, Any],
        task_type: str = "set_state",
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Publish a task to *subject* and wait for a correlated result.

        This is a **non-blocking** method — it yields control back to the
        event loop while waiting for the agent's reply on ``tasks.completed``.

        Args:
            subject: NATS subject to publish the task to (e.g. ``tasks.lighting``).
            payload: Type-specific parameters as a dict (the agent receives
                this as a ``json.RawMessage``).
            task_type: The operation type (e.g. ``"set_state"``).
            timeout: Maximum seconds to wait for a result.

        Returns:
            The result ``dict`` as published by the agent.

        Raises:
            ConnectionError: If the orchestrator is not connected to NATS.
            asyncio.TimeoutError: If no correlated result arrives within
                *timeout* seconds.
            json.JSONDecodeError: If the agent's reply is malformed JSON.
        """
        # Track total dispatched tasks.
        self._task_count += 1

        try:
            for attempt in range(1, 4):
                task_id = uuid4().hex
                try:
                    if self.nc is None:
                        raise ConnectionError(
                            "Orchestrator is not connected to NATS. Call `await connect()` first."
                        )

                    # 1. Build the task model.
                    task = TaskModel(
                        id=task_id,
                        type=task_type,
                        payload=payload,
                        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    )

                    # 2. Create a Future that will be resolved when the result arrives.
                    future = asyncio.get_event_loop().create_future()

                    # 3. Store it in the pending map BEFORE publishing to avoid a race
                    #    condition where the agent replies before we start listening.
                    self._pending[task_id] = future

                    # 4. Serialise and publish.
                    raw = task.model_dump_json().encode("utf-8")
                    await self.nc.publish(subject, raw)

                    logger.info(
                        "Task %s (%s) published to '%s' | payload_keys=%s",
                        task.id,
                        task.type,
                        subject,
                        list(payload.keys()),
                    )

                    # 5. Await the correlated result (or timeout).
                    return await asyncio_wait_for(future, timeout=timeout)

                except (TimeoutError, ConnectionError) as e:
                    self._pending.pop(task_id, None)
                    if attempt < 3:
                        logger.warning("Retry %d/3 for task %s due to %s", attempt, task_id, e)
                        await asyncio.sleep(1)
                    else:
                        raise e
                except Exception:
                    self._pending.pop(task_id, None)
                    raise
        finally:
            logger.info("Total tasks dispatched: %d", self._task_count)

    # ── Internal result handler ─────────────────────────────────────────

    async def _on_result(self, msg: NatsMsg) -> None:
        """Callback invoked when a message arrives on ``tasks.completed``.

        Parses the message body as a ``ResultModel``, looks up the
        corresponding ``Future`` in ``_pending``, and resolves it.

        If the message is malformed or refers to an unknown task, it is
        logged and discarded — the caller's ``Future`` remains pending and
        will eventually time out.
        """
        raw = msg.data.decode("utf-8")

        # 1. Try to parse the result JSON.
        try:
            result = ResultModel.model_validate_json(raw)
        except Exception as exc:
            logger.error(
                "Failed to parse result JSON: %s | raw_data=%.200s",
                exc,
                raw,
            )
            return

        logger.debug("Result received: task_id=%s success=%s", result.task_id, result.success)

        # 2. Look up the pending Future.
        future = self._pending.pop(result.task_id, None)
        if future is None:
            logger.warning(
                "Received result for unknown/cancelled task '%s' — ignoring",
                result.task_id,
            )
            return

        # 3. Resolve the Future with the result dict (not the model, so async
        #    callers can use the raw dict format consistent with the agent wire
        #    format).
        if not future.done():
            future.set_result(result.model_dump())
        else:
            logger.debug(
                "Future for task '%s' already done — discarding duplicate result",
                result.task_id,
            )


# ── Compatibility helper ─────────────────────────────────────────────────────

async def asyncio_wait_for(future: Any, *, timeout: float) -> Any:
    """Await a future with a timeout.

    Wraps ``asyncio.wait_for`` but raises the built-in ``TimeoutError``
    instead of ``asyncio.TimeoutError`` so that callers can catch the
    standard Python exception.

    Args:
        future: The ``asyncio.Future`` to await.
        timeout: Maximum number of seconds to wait.

    Returns:
        The future's result.

    Raises:
        TimeoutError: If *timeout* seconds elapse before the future resolves.
    """
    import asyncio

    try:
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Task timed out after {timeout:.1f}s") from None
