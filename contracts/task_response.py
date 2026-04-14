from typing import Any

from pydantic import BaseModel, Field

from contracts.task_request import ClarificationItem, InputStatus, TaskRequest


class TaskResponse(BaseModel):
    request_id: str
    status: InputStatus
    validation_errors: list[ClarificationItem] = Field(default_factory=list)
    normalized_request: dict[str, Any]
    model: str | None = None
    answer: str

    @classmethod
    def from_clarification_request(cls, task_request: TaskRequest) -> "TaskResponse":
        return cls(
            request_id=task_request.request_id,
            status=task_request.input_status,
            validation_errors=task_request.clarification_items,
            normalized_request=task_request.model_dump(mode="json"),
            answer=build_clarification_message(task_request=task_request),
        )

    @classmethod
    def from_planned_task(
        cls, task_request: TaskRequest, model: str, answer: str
    ) -> "TaskResponse":
        return cls(
            request_id=task_request.request_id,
            status=task_request.input_status,
            validation_errors=[],
            normalized_request=task_request.model_dump(mode="json"),
            model=model,
            answer=answer,
        )


def build_clarification_message(task_request: TaskRequest) -> str:
    clarification_lines = [
        "Request requires clarification before planning.",
        "",
        "Missing or incomplete fields:",
    ]
    for item in task_request.clarification_items:
        clarification_lines.append(f"- {item.field_name}: {item.reason}")
    return "\n".join(clarification_lines)
