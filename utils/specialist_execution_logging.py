from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Sequence

from langchain_core.tools import BaseTool
from pydantic import ConfigDict, Field

SENSITIVE_FIELD_MARKERS = {
    "secret",
    "token",
    "password",
    "passwd",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
}
MAX_STRING_LENGTH = 1000


class LoggedBaseToolProxy(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    original_tool: BaseTool
    audit_logger: "SpecialistExecutionAuditLogger"
    name: str
    description: str
    args_schema: Any = Field(default=None, exclude=True)
    return_direct: bool = False
    response_format: str = "content"

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        tool_input = normalize_tool_payload(args, kwargs)
        tool_call_id = self.audit_logger.record_tool_call_started(
            tool_name=self.name,
            tool_input=tool_input,
        )
        try:
            result = self.original_tool.invoke(tool_input)
        except Exception as exc:
            self.audit_logger.record_tool_call_failed(
                tool_call_id=tool_call_id,
                tool_name=self.name,
                error=exc,
            )
            raise
        self.audit_logger.record_tool_call_succeeded(
            tool_call_id=tool_call_id,
            tool_name=self.name,
            tool_output=result,
        )
        return result

    async def _arun(self, *args: Any, **kwargs: Any) -> Any:
        tool_input = normalize_tool_payload(args, kwargs)
        tool_call_id = self.audit_logger.record_tool_call_started(
            tool_name=self.name,
            tool_input=tool_input,
        )
        try:
            result = await self.original_tool.ainvoke(tool_input)
        except Exception as exc:
            self.audit_logger.record_tool_call_failed(
                tool_call_id=tool_call_id,
                tool_name=self.name,
                error=exc,
            )
            raise
        self.audit_logger.record_tool_call_succeeded(
            tool_call_id=tool_call_id,
            tool_name=self.name,
            tool_output=result,
        )
        return result


class SpecialistExecutionAuditLogger:
    def __init__(
        self,
        *,
        owner_agent: str,
        request_id: str | None = None,
        step_id: str | None = None,
        user_id: str | None = None,
        input_snapshot: Any = None,
    ) -> None:
        self.owner_agent = owner_agent
        self.request_id = request_id
        self.step_id = step_id
        self.user_id = user_id
        self.input_snapshot = sanitize_for_audit(input_snapshot)
        self.started_at = utc_now()
        self._lock = Lock()
        self._event_index = 0
        self._tool_call_index = 0
        self._audit_events: list[dict[str, Any]] = []
        self._tool_calls: list[dict[str, Any]] = []

    def record_input_received(self, payload: Any) -> None:
        self.input_snapshot = sanitize_for_audit(payload)
        self.record_event(
            event_type="input_received",
            summary="Specialist agent received normalized working input.",
            payload={"working_input": self.input_snapshot},
        )

    def record_decision(
        self,
        *,
        summary: str,
        decision_type: str,
        payload: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> None:
        self.record_event(
            event_type="decision_recorded",
            summary=summary,
            payload={
                "decision_type": decision_type,
                **dict(payload or {}),
            },
            status=status,
        )

    def record_error(
        self,
        *,
        summary: str,
        error: Any,
        status: str = "failed",
    ) -> None:
        self.record_event(
            event_type="error_recorded",
            summary=summary,
            payload={"error": sanitize_for_audit(error)},
            status=status,
        )

    def record_tool_call_started(
        self,
        *,
        tool_name: str,
        tool_input: Any,
    ) -> str:
        with self._lock:
            self._tool_call_index += 1
            tool_call_id = f"{self.step_id or 'step'}-tool-{self._tool_call_index}"
            call_record = {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "name": tool_name,
                "summary": tool_name,
                "status": "started",
                "started_at": utc_now().isoformat(),
                "request": sanitize_for_audit(tool_input),
            }
            self._tool_calls.append(call_record)
        self.record_event(
            event_type="tool_call_started",
            summary=f"Tool `{tool_name}` invoked for specialist analysis.",
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "request": sanitize_for_audit(tool_input),
            },
            status="running",
        )
        return tool_call_id

    def record_tool_call_succeeded(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        tool_output: Any,
    ) -> None:
        response_payload = sanitize_for_audit(tool_output)
        with self._lock:
            for tool_call in self._tool_calls:
                if tool_call["tool_call_id"] != tool_call_id:
                    continue
                tool_call["status"] = "completed"
                tool_call["completed_at"] = utc_now().isoformat()
                tool_call["response"] = response_payload
                break
        self.record_event(
            event_type="tool_call_completed",
            summary=f"Tool `{tool_name}` returned successfully.",
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "response": response_payload,
            },
            status="completed",
        )

    def record_tool_call_failed(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        error: Exception,
    ) -> None:
        error_payload = {
            "exception_type": type(error).__name__,
            "message": str(error),
        }
        with self._lock:
            for tool_call in self._tool_calls:
                if tool_call["tool_call_id"] != tool_call_id:
                    continue
                tool_call["status"] = "failed"
                tool_call["completed_at"] = utc_now().isoformat()
                tool_call["error"] = error_payload
                break
        self.record_event(
            event_type="tool_call_failed",
            summary=f"Tool `{tool_name}` failed during specialist analysis.",
            payload={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "error": sanitize_for_audit(error_payload),
            },
            status="failed",
        )

    def record_event(
        self,
        *,
        event_type: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> None:
        with self._lock:
            self._event_index += 1
            self._audit_events.append(
                build_audit_event(
                    owner_agent=self.owner_agent,
                    request_id=self.request_id,
                    step_id=self.step_id,
                    user_id=self.user_id,
                    event_id=f"{self.step_id or self.owner_agent}-event-{self._event_index}",
                    event_type=event_type,
                    summary=summary,
                    payload=payload,
                    status=status,
                )
            )

    def build_execution_details(self, *, final_status: str | None = None) -> dict[str, Any]:
        return {
            "owner_agent": self.owner_agent,
            "request_id": self.request_id,
            "step_id": self.step_id,
            "user_id": self.user_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": utc_now().isoformat(),
            "input_snapshot": self.input_snapshot,
            "final_status": final_status,
            "audit_events": list(self._audit_events),
            "tool_calls": list(self._tool_calls),
        }


def wrap_specialist_tools(
    tools: Sequence[Any],
    audit_logger: SpecialistExecutionAuditLogger,
) -> list[Any]:
    wrapped_tools: list[Any] = []
    for tool in tools:
        if isinstance(tool, BaseTool):
            wrapped_tools.append(
                LoggedBaseToolProxy(
                    original_tool=tool,
                    audit_logger=audit_logger,
                    name=tool.name,
                    description=tool.description,
                    args_schema=getattr(tool, "args_schema", None),
                    return_direct=getattr(tool, "return_direct", False),
                    response_format=getattr(tool, "response_format", "content"),
                )
            )
            continue
        wrapped_tools.append(tool)
    return wrapped_tools


def attach_execution_details(
    *,
    output: Any,
    audit_logger: SpecialistExecutionAuditLogger,
) -> Any:
    existing_details = (
        dict(getattr(output, "execution_details", {}) or {})
        if getattr(output, "execution_details", None) is not None
        else {}
    )
    collector_details = audit_logger.build_execution_details(
        final_status=str(getattr(output, "status", None) or "")
    )
    existing_audit_events = list(existing_details.get("audit_events") or [])
    existing_tool_calls = list(existing_details.get("tool_calls") or [])
    output.execution_details = {
        **collector_details,
        **existing_details,
        "input_snapshot": existing_details.get("input_snapshot")
        or collector_details["input_snapshot"],
        "final_status": existing_details.get("final_status")
        or collector_details["final_status"],
        "audit_events": collector_details["audit_events"] + existing_audit_events,
        "tool_calls": collector_details["tool_calls"] + existing_tool_calls,
    }
    return output


def append_output_audit_event(
    *,
    output: Any,
    owner_agent: str,
    summary: str,
    event_type: str,
    payload: dict[str, Any] | None = None,
    status: str | None = None,
    request_id: str | None = None,
    step_id: str | None = None,
    user_id: str | None = None,
) -> None:
    execution_details = dict(getattr(output, "execution_details", {}) or {})
    audit_events = list(execution_details.get("audit_events") or [])
    audit_events.append(
        build_audit_event(
            owner_agent=owner_agent,
            request_id=request_id,
            step_id=step_id,
            user_id=user_id,
            event_id=f"{step_id or owner_agent}-event-{len(audit_events) + 1}",
            event_type=event_type,
            summary=summary,
            payload=payload,
            status=status,
        )
    )
    execution_details["audit_events"] = audit_events
    execution_details.setdefault("tool_calls", [])
    execution_details.setdefault("owner_agent", owner_agent)
    execution_details.setdefault("request_id", request_id)
    execution_details.setdefault("step_id", step_id)
    execution_details.setdefault("user_id", user_id)
    getattr(output, "execution_details", None)
    output.execution_details = execution_details


def build_audit_event(
    *,
    owner_agent: str,
    request_id: str | None,
    step_id: str | None,
    user_id: str | None,
    event_id: str,
    event_type: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "timestamp": utc_now().isoformat(),
        "owner_agent": owner_agent,
        "request_id": request_id,
        "step_id": step_id,
        "user_id": user_id,
        "event_type": event_type,
        "status": status,
        "summary": summary,
        "payload": sanitize_for_audit(payload or {}),
    }


def normalize_tool_payload(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    if kwargs and not args:
        return kwargs
    if len(args) == 1 and not kwargs:
        return args[0]
    if not args and not kwargs:
        return {}
    return {
        "args": list(args),
        "kwargs": kwargs,
    }


def sanitize_for_audit(value: Any, field_name: str | None = None) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key)
            sanitized[normalized_key] = sanitize_for_audit(
                item,
                field_name=normalized_key,
            )
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_audit(item, field_name=field_name) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_audit(item, field_name=field_name) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, BaseTool):
        return {"tool_name": value.name}
    if should_mask_value(field_name):
        return "[REDACTED]"
    if isinstance(value, str):
        normalized_value = value.strip()
        if len(normalized_value) > MAX_STRING_LENGTH:
            return normalized_value[:MAX_STRING_LENGTH] + "...[truncated]"
        return normalized_value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if hasattr(value, "model_dump"):
        return sanitize_for_audit(value.model_dump(mode="json"), field_name=field_name)
    if hasattr(value, "isoformat") and callable(value.isoformat):
        return value.isoformat()
    return truncate_text(repr(value))


def should_mask_value(field_name: str | None) -> bool:
    if not field_name:
        return False
    normalized_name = field_name.strip().lower()
    return any(marker in normalized_name for marker in SENSITIVE_FIELD_MARKERS)


def truncate_text(value: str) -> str:
    if len(value) <= MAX_STRING_LENGTH:
        return value
    return value[:MAX_STRING_LENGTH] + "...[truncated]"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
