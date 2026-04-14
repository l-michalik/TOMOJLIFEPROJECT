from typing import Any

from pydantic import BaseModel, Field

from contracts.task_context import TaskContext


class TaskRequest(BaseModel):
    request_id: str
    source: str
    user_id: str
    task_description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    context: TaskContext = Field(default_factory=TaskContext)

    def to_prompt(self) -> str:
        return (
            "Prepare a Supervisor response for the DevOps task below.\n\n"
            f"request_id: {self.request_id}\n"
            f"source: {self.source}\n"
            f"user_id: {self.user_id}\n"
            f"task_description: {self.task_description}\n"
            f"parameters: {self.parameters}\n"
            f"context.environment: {self.context.environment}\n"
            f"context.priority: {self.context.priority}\n"
            f"context.ticket_id: {self.context.ticket_id}\n"
            f"context.conversation_id: {self.context.conversation_id}\n\n"
            "Respond in 3 sections:\n"
            "1. Short task summary.\n"
            "2. Plan steps with assigned specialist agents.\n"
            "3. Risks or actions that require approval.\n"
        )
