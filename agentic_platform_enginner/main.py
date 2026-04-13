from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:
    package_root = Path(__file__).resolve().parent.parent
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

from agentic_platform_enginner.schema.input_schema import (
    ValidationError,
    build_supervisor_input,
    export_task_input_schema,
    get_task_input_schema,
    validate_task_input,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the formal input contract of the Agentic Platform Engineer system."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Path to the JSON file containing the input payload.",
    )
    parser.add_argument(
        "--print-schema",
        action="store_true",
        help="Print the current JSON Schema to stdout.",
    )
    parser.add_argument(
        "--export-schema",
        action="store_true",
        help="Write the JSON Schema to docs/task_input_schema.json.",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="After validation, print the normalized supervisor contract.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.export_schema:
        output_path = export_task_input_schema()
        print(f"Schema exported to: {output_path}")

    if args.print_schema:
        print(json.dumps(get_task_input_schema(), ensure_ascii=True, indent=2))

    if args.input is None:
        return 0

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    validated = validate_task_input(payload)

    if args.normalize:
        print(json.dumps(build_supervisor_input(validated), ensure_ascii=True, indent=2))
    else:
        print(json.dumps(validated, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(f"Validation error: {error}")
        raise SystemExit(1) from error
