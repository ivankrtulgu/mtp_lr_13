from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from orchestrator.core import AgentOrchestrator

# ── Models ──────────────────────────────────────────────────────────────────────

class TaskRequest(BaseModel):
    """Request body for triggering a task in the Multi-Agent System."""

    subject: str = Field(..., description="The NATS subject (e.g. 'tasks.lighting')")
    payload: dict[str, Any] = Field(..., description="The task parameters")
    task_type: str = Field("set_state", description="The operation type")
    timeout: float = Field(30.0, description="Maximum seconds to wait for a result")


# ── Lifecycle ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage the AgentOrchestrator lifecycle."""
    # Instantiate the orchestrator and connect to NATS
    orchestrator = AgentOrchestrator()
    try:
        await orchestrator.connect()
        # Store the orchestrator in app.state for access in endpoints
        app.state.orchestrator = orchestrator
        yield
    finally:
        # Gracefully shut down the NATS connection
        await orchestrator.close()


# ── Application ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Smart Home Orchestrator API",
    description="REST API to trigger tasks in the Multi-Agent System via HTTP",
    lifespan=lifespan,
)


# ── Endpoints ───────────────────────────────────────────────────────────────────

@app.post("/tasks")
async def trigger_task(request: Request, task_req: TaskRequest):
    """
    Trigger a task in the Multi-Agent System.

    Sends a task to the specified NATS subject and waits for the result.
    """
    orchestrator: AgentOrchestrator = request.app.state.orchestrator

    try:
        result = await orchestrator.send_task(
            subject=task_req.subject,
            payload=task_req.payload,
            task_type=task_req.task_type,
            timeout=task_req.timeout,
        )
        return result

    except TimeoutError as e:
        raise HTTPException(
            status_code=504,
            detail=f"Gateway Timeout: {str(e)}",
        )
    except ConnectionError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Service Unavailable: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(e)}",
        )
