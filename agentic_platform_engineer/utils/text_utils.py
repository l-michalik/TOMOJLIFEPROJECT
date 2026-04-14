from __future__ import annotations

import re

from agentic_platform_engineer.contracts.supervisor_input import JsonValue, RawJsonObject


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip().lower()
    return normalized_value or None


def read_string(payload: RawJsonObject, field_name: str) -> str | None:
    value = payload.get(field_name)
    return read_string_value(value)


def read_string_value(value: JsonValue | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized_value = value.strip()
    return normalized_value or None


def match_group(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    if match is None:
        return None
    return match.group("value")
