"""Workflow result contract."""

from pydantic import BaseModel


class WorkflowResult(BaseModel):
    """STUB: see Task 3.2 for full implementation."""

    success: bool = True
