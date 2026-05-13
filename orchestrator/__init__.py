"""Agent Orchestrator — Smart Home Multi-Agent System.

A production-grade Python orchestrator that coordinates agents via NATS
using a request-response messaging pattern.
"""

__version__ = "1.0.0"
__all__ = [
    "AgentOrchestrator",
    "TaskModel",
    "ResultModel",
    "LightingPayload",
]

from orchestrator.core import AgentOrchestrator
from orchestrator.models import LightingPayload, ResultModel, TaskModel
