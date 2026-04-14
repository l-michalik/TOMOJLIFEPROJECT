from __future__ import annotations

from agentic_platform_engineer.contracts.supervisor_input import RawJsonObject


def get_object(payload: RawJsonObject | None, field_name: str) -> RawJsonObject | None:
    if payload is None or field_name not in payload:
        return None

    value = payload[field_name]
    if not isinstance(value, dict):
        return None
    return value


def build_field_path(field_name: str, parent_path: str | None) -> str:
    if parent_path is None:
        return field_name
    return f"{parent_path}.{field_name}"
