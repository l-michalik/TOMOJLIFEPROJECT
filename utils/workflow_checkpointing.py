from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.sqlite import SqliteSaver

from contracts.task_request import TaskRequest
from contracts.task_response import TaskResponse

DEFAULT_CHECKPOINT_NAMESPACE = "supervisor"
DEFAULT_CHECKPOINT_DB_PATH = Path(
    os.getenv(
        "WORKFLOW_CHECKPOINT_DB_PATH",
        ".runtime/langgraph_supervisor_checkpoints.sqlite",
    )
)


@dataclass(slots=True)
class WorkflowCheckpointRecord:
    checkpoint_id: str
    parent_checkpoint_id: str | None
    thread_id: str
    checkpoint_ns: str
    created_at: datetime
    event: str
    task_request: dict[str, Any]
    task_response: dict[str, Any]


class WorkflowCheckpointStore:
    def __init__(
        self,
        db_path: Path = DEFAULT_CHECKPOINT_DB_PATH,
        checkpoint_namespace: str = DEFAULT_CHECKPOINT_NAMESPACE,
    ) -> None:
        self._db_path = db_path
        self._checkpoint_namespace = checkpoint_namespace
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
        self._saver = SqliteSaver(self._connection)
        self._saver.setup()

    def load_latest(
        self,
        request_id: str,
    ) -> tuple[TaskRequest, TaskResponse] | None:
        checkpoint_tuple = self._saver.get_tuple(self._build_thread_config(request_id))
        if checkpoint_tuple is None:
            return None
        checkpoint_payload = checkpoint_tuple.checkpoint["channel_values"]
        return (
            TaskRequest.model_validate(checkpoint_payload["task_request"]),
            TaskResponse.model_validate(checkpoint_payload["task_response"]),
        )

    def save(
        self,
        request_id: str,
        task_request: TaskRequest,
        task_response: TaskResponse,
        event: str,
    ) -> WorkflowCheckpointRecord:
        latest_checkpoint = self._saver.get_tuple(self._build_thread_config(request_id))
        created_at = utc_now()
        checkpoint = empty_checkpoint()

        task_response.state.resume_data.checkpoint_id = checkpoint["id"]
        task_response.state.resume_data.resume_token = f"{request_id}:resume:{checkpoint['id']}"
        task_response.state.timestamps.updated_at = created_at

        task_request_payload = task_request.model_dump(mode="json")
        task_response_payload = task_response.model_dump(mode="json")
        checkpoint["channel_values"] = {
            "task_request": task_request_payload,
            "task_response": task_response_payload,
        }

        saved_config = self._saver.put(
            config=latest_checkpoint.config
            if latest_checkpoint is not None
            else self._build_thread_config(request_id),
            checkpoint=checkpoint,
            metadata={
                "source": event,
                "thread_id": request_id,
                "event": event,
                "writes": {
                    "task_request": task_request_payload,
                    "task_response": task_response_payload,
                },
            },
            new_versions={},
        )
        return WorkflowCheckpointRecord(
            checkpoint_id=saved_config["configurable"]["checkpoint_id"],
            parent_checkpoint_id=(
                latest_checkpoint.config["configurable"]["checkpoint_id"]
                if latest_checkpoint is not None
                else None
            ),
            thread_id=request_id,
            checkpoint_ns=self._checkpoint_namespace,
            created_at=created_at,
            event=event,
            task_request=task_request_payload,
            task_response=task_response_payload,
        )

    def delete(self, request_id: str) -> None:
        self._saver.delete_thread(request_id)

    def _build_thread_config(self, request_id: str) -> dict[str, Any]:
        return {
            "configurable": {
                "thread_id": request_id,
                "checkpoint_ns": self._checkpoint_namespace,
            }
        }


_workflow_checkpoint_store = WorkflowCheckpointStore()


def get_workflow_checkpoint_store() -> WorkflowCheckpointStore:
    return _workflow_checkpoint_store


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
