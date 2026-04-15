from __future__ import annotations

import argparse
import ast
import inspect
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.task_request import (  # noqa: E402
    OperationType,
    RequestSource,
    TargetEnvironment,
    TaskParams,
    TaskPriority,
    TaskRequest,
)
from contracts.task_response import WorkflowPlanStep  # noqa: E402
from agents import supervisor as supervisor_module  # noqa: E402
from utils.workflow_plan_builder import build_workflow_plan  # noqa: E402


DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "diagrams"
DEFAULT_MERMAID_PATH = DEFAULT_OUTPUT_DIR / "agent_workflow_flow.mmd"
DEFAULT_SVG_PATH = DEFAULT_OUTPUT_DIR / "agent_workflow_flow.svg"
DEFAULT_PNG_PATH = DEFAULT_OUTPUT_DIR / "agent_workflow_flow.png"
MAX_LABEL_LENGTH = 72
DEFAULT_PNG_SCALE = 3


@dataclass
class WorkflowScenario:
    key: str
    title: str
    operation_types: list[OperationType]
    target_environment: TargetEnvironment
    constraints: list[str]
    plan: list[WorkflowPlanStep]


def build_mermaid_diagram() -> str:
    lines = ["flowchart TD"]
    lines.extend(build_supervisor_ast_subgraphs())
    lines.append("")

    scenarios = discover_workflow_scenarios()
    for scenario in scenarios:
        lines.extend(build_scenario_subgraph(scenario))
        lines.append("")

    for scenario in scenarios:
        lines.append(f"    RUN_SUPERVISOR_AGENT_ENTRY --> {scenario.key.upper()}_START")
    return "\n".join(lines)


def build_supervisor_ast_subgraphs() -> list[str]:
    function_names = [
        "run_supervisor_agent",
        "resume_supervisor_workflow",
        "continue_supervisor_workflow",
        "run_supervisor_planning",
        "build_fallback_planning_result",
    ]
    lines: list[str] = []
    previous_exit: str | None = None

    for function_name in function_names:
        function_object = getattr(supervisor_module, function_name)
        function_lines, entry_node_id, exit_node_ids = build_function_subgraph(
            function_name=function_name,
            function_object=function_object,
        )
        lines.extend(function_lines)
        if previous_exit:
            lines.append(f"    {previous_exit} -. next call .-> {entry_node_id}")
        if function_name == "run_supervisor_agent":
            lines.append(f"    {entry_node_id}:::entry")
        previous_exit = exit_node_ids[-1] if exit_node_ids else entry_node_id

    lines.append("    classDef entry fill:#e8f1ff,stroke:#4a6fa5,stroke-width:2px;")
    return lines


def build_function_subgraph(function_name: str, function_object: object) -> tuple[list[str], str, list[str]]:
    function_id = function_name.upper()
    source = dedent(inspect.getsource(function_object))
    function_def = ast.parse(source).body[0]
    assert isinstance(function_def, ast.FunctionDef)

    lines = [f'    subgraph {function_id}["{function_name}()"]']
    entry_node_id = f"{function_id}_ENTRY"
    lines.append(f'        {entry_node_id}["{function_name}() entry"]')
    body_lines, body_entry, exit_node_ids = build_statement_flow(
        statements=function_def.body,
        function_id=function_id,
        counter=[0],
    )
    lines.extend(body_lines)
    if body_entry:
        lines.append(f"        {entry_node_id} --> {body_entry}")
    for exit_node_id in exit_node_ids:
        lines.append(f"        {exit_node_id} --> {function_id}_EXIT")
    lines.append(f'        {function_id}_EXIT["{function_name}() exit"]')
    lines.append("    end")
    return lines, entry_node_id, [f"{function_id}_EXIT"]


def build_statement_flow(
    statements: list[ast.stmt],
    function_id: str,
    counter: list[int],
) -> tuple[list[str], str | None, list[str]]:
    lines: list[str] = []
    entry_node_id: str | None = None
    pending_exit_node_ids: list[str] = []

    for statement in statements:
        statement_lines, statement_entry, statement_exits = build_statement_node(
            statement=statement,
            function_id=function_id,
            counter=counter,
        )
        lines.extend(statement_lines)
        if statement_entry and entry_node_id is None:
            entry_node_id = statement_entry
        if pending_exit_node_ids and statement_entry:
            for pending_exit_node_id in pending_exit_node_ids:
                lines.append(f"        {pending_exit_node_id} --> {statement_entry}")
        pending_exit_node_ids = statement_exits

    return lines, entry_node_id, pending_exit_node_ids


def build_statement_node(
    statement: ast.stmt,
    function_id: str,
    counter: list[int],
) -> tuple[list[str], str | None, list[str]]:
    if isinstance(statement, ast.If):
        return build_if_flow(statement=statement, function_id=function_id, counter=counter)
    return build_linear_statement(statement=statement, function_id=function_id, counter=counter)


def build_if_flow(
    statement: ast.If,
    function_id: str,
    counter: list[int],
) -> tuple[list[str], str, list[str]]:
    lines: list[str] = []
    condition_node_id = next_node_id(function_id, counter)
    lines.append(
        f'        {condition_node_id}{{"{sanitize_mermaid_text(ast.unparse(statement.test), is_condition=True)}"}}'
    )

    body_lines, body_entry, body_exits = build_statement_flow(
        statements=statement.body,
        function_id=function_id,
        counter=counter,
    )
    lines.extend(body_lines)

    orelse_lines, orelse_entry, orelse_exits = build_statement_flow(
        statements=statement.orelse,
        function_id=function_id,
        counter=counter,
    )
    lines.extend(orelse_lines)

    if body_entry:
        lines.append(f'        {condition_node_id} -- "true" --> {body_entry}')
    else:
        body_exits = [condition_node_id]

    if orelse_entry:
        lines.append(f'        {condition_node_id} -- "false" --> {orelse_entry}')
    else:
        orelse_exits = [condition_node_id]

    return lines, condition_node_id, body_exits + orelse_exits


def build_linear_statement(
    statement: ast.stmt,
    function_id: str,
    counter: list[int],
) -> tuple[list[str], str, list[str]]:
    node_id = next_node_id(function_id, counter)
    label = build_statement_label(statement)
    lines = [f'        {node_id}["{sanitize_mermaid_text(label)}"]']
    return lines, node_id, [] if isinstance(statement, (ast.Return, ast.Raise)) else [node_id]


def build_scenario_subgraph(scenario: WorkflowScenario) -> list[str]:
    scenario_id = scenario.key.upper()
    lines = [f'    subgraph {scenario_id}["{scenario.title}"]']
    lines.append(
        f'        {scenario_id}_START["{build_scenario_start_label(scenario)}"]'
    )

    for step in scenario.plan:
        lines.append(f"        {build_node_id(scenario_id, step)}[{build_step_label(step)}]")

    for step in scenario.plan:
        node_id = build_node_id(scenario_id, step)
        if step.depends_on:
            for dependency in step.depends_on:
                lines.append(
                    f"        {build_dependency_node_id(scenario_id, dependency)} --> {node_id}"
                )
        else:
            lines.append(f"        {scenario_id}_START --> {node_id}")

    terminal_steps = {
        step.step_id
        for step in scenario.plan
        if not any(step.step_id in other.depends_on for other in scenario.plan)
    }
    lines.append(f'        {scenario_id}_END["Workflow terminal branch"]')
    for step_id in sorted(terminal_steps):
        lines.append(f"        {scenario_id}_{step_id.replace('-', '_')} --> {scenario_id}_END")
    lines.append("    end")
    return lines


def build_scenario_request(scenario: WorkflowScenario) -> TaskRequest:
    service_name = "payments-api"
    environment = scenario.target_environment.value
    operation = scenario.operation_types[0].value
    constraints_fragment = ""
    if scenario.constraints:
        constraints_fragment = f" with constraints {', '.join(scenario.constraints)}"

    return TaskRequest(
        request_id=f"diagram-{scenario.key}",
        source=RequestSource.API,
        user_id="diagram-generator",
        user_request=(
            f"{operation} {service_name} to {environment}{constraints_fragment}"
        ),
        params=TaskParams(
            target_environment=scenario.target_environment,
            priority=TaskPriority.HIGH,
            execution_options={
                "service_name": service_name,
                "operation_type": operation,
                "constraints": list(scenario.constraints),
            },
        ),
    )


def build_node_id(scenario_id: str, step: WorkflowPlanStep) -> str:
    return f"{scenario_id}_{step.step_id.replace('-', '_')}"


def build_dependency_node_id(scenario_id: str, dependency_step_id: str) -> str:
    return f"{scenario_id}_{dependency_step_id.replace('-', '_')}"


def build_step_label(step: WorkflowPlanStep) -> str:
    label_lines = [
        step.step_id,
        step.task_type.value,
        step.owner_agent.value,
        f"status={step.status.value}",
    ]
    return '"' + "<br/>".join(escape_mermaid_label(line) for line in label_lines) + '"'


def escape_mermaid_label(value: str) -> str:
    return value.replace('"', "'")


def discover_workflow_scenarios() -> list[WorkflowScenario]:
    scenario_candidates: list[tuple[TargetEnvironment, list[str]]] = [
        (TargetEnvironment.STAGE, []),
        (TargetEnvironment.PROD, ["requires_approval"]),
    ]
    grouped_scenarios: dict[
        tuple[tuple[str, str, str, tuple[str, ...]], ...],
        WorkflowScenario,
    ] = {}

    for environment, constraints in scenario_candidates:
        for operation_type in OperationType:
            task_request = build_discovery_request(
                operation_type=operation_type,
                target_environment=environment,
                constraints=constraints,
            )
            plan = build_workflow_plan(task_request)
            signature = build_plan_signature(plan)

            if signature not in grouped_scenarios:
                grouped_scenarios[signature] = WorkflowScenario(
                    key=build_scenario_key(
                        operation_type=operation_type,
                        target_environment=environment,
                        constraints=constraints,
                    ),
                    title="",
                    operation_types=[operation_type],
                    target_environment=environment,
                    constraints=list(constraints),
                    plan=plan,
                )
                continue

            grouped_scenarios[signature].operation_types.append(operation_type)

    scenarios = list(grouped_scenarios.values())
    for scenario in scenarios:
        scenario.title = build_scenario_title(scenario)
    return sorted(scenarios, key=lambda item: item.key)


def build_discovery_request(
    operation_type: OperationType,
    target_environment: TargetEnvironment,
    constraints: list[str],
) -> TaskRequest:
    return TaskRequest(
        request_id=f"diagram-{target_environment.value}-{operation_type.value}",
        source=RequestSource.API,
        user_id="diagram-generator",
        user_request=(
            f"{operation_type.value} payments-api to {target_environment.value}"
        ),
        params=TaskParams(
            target_environment=target_environment,
            priority=TaskPriority.HIGH,
            execution_options={
                "service_name": "payments-api",
                "operation_type": operation_type.value,
                "constraints": list(constraints),
            },
        ),
    )


def build_plan_signature(
    plan: list[WorkflowPlanStep],
) -> tuple[tuple[str, str, str, tuple[str, ...]], ...]:
    return tuple(
        (
            step.task_type.value,
            step.owner_agent.value,
            step.status.value,
            tuple(step.depends_on),
        )
        for step in plan
    )


def build_scenario_key(
    operation_type: OperationType,
    target_environment: TargetEnvironment,
    constraints: list[str],
) -> str:
    suffix = "approval" if constraints else "default"
    return f"{target_environment.value}_{operation_type.value}_{suffix}"


def build_scenario_title(scenario: WorkflowScenario) -> str:
    operations = "/".join(operation.value for operation in scenario.operation_types)
    approval = " approval-gated" if scenario.constraints else ""
    return f"{operations} on {scenario.target_environment.value}{approval}"


def build_scenario_start_label(scenario: WorkflowScenario) -> str:
    operations = "/".join(operation.value for operation in scenario.operation_types)
    constraints = ""
    if scenario.constraints:
        constraints = f" with {', '.join(scenario.constraints)}"
    return f"{operations} -> build_workflow_plan(){constraints}"


def next_node_id(function_id: str, counter: list[int]) -> str:
    counter[0] += 1
    return f"{function_id}_NODE_{counter[0]}"


def build_statement_label(statement: ast.stmt) -> str:
    if isinstance(statement, ast.Assign):
        return f"{ast.unparse(statement.targets[0])} = {ast.unparse(statement.value)}"
    if isinstance(statement, ast.AnnAssign):
        return f"{ast.unparse(statement.target)} = {ast.unparse(statement.value)}"
    if isinstance(statement, ast.Expr):
        return ast.unparse(statement.value)
    if isinstance(statement, ast.Return):
        return f"return {ast.unparse(statement.value)}" if statement.value else "return"
    if isinstance(statement, ast.Raise):
        return f"raise {ast.unparse(statement.exc)}" if statement.exc else "raise"
    return ast.unparse(statement)


def sanitize_mermaid_text(value: str, is_condition: bool = False) -> str:
    compact = " ".join(value.split())
    compact = compact.replace('"', "'")
    compact = compact.replace("{", "(").replace("}", ")")
    compact = compact.replace("[", "(").replace("]", ")")
    if len(compact) > MAX_LABEL_LENGTH:
        compact = compact[: MAX_LABEL_LENGTH - 3] + "..."
    if is_condition:
        return compact
    return compact.replace("->", "to")


def render_diagram(
    mermaid_path: Path,
    output_path: Path,
    scale: int | None = None,
) -> bool:
    mermaid_cli = shutil.which("mmdc")
    if not mermaid_cli:
        return False

    command = [mermaid_cli, "-i", str(mermaid_path), "-o", str(output_path)]
    if scale is not None:
        command.extend(["-s", str(scale)])

    subprocess.run(command, check=True)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Mermaid agent workflow diagram and optional PNG output."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated Mermaid and PNG files.",
    )
    parser.add_argument(
        "--png-scale",
        type=int,
        default=DEFAULT_PNG_SCALE,
        help="Raster scale factor used when rendering the PNG output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    mermaid_path = output_dir / DEFAULT_MERMAID_PATH.name
    svg_path = output_dir / DEFAULT_SVG_PATH.name
    png_path = output_dir / DEFAULT_PNG_PATH.name
    mermaid_path.write_text(build_mermaid_diagram(), encoding="utf-8")

    try:
        rendered_svg = render_diagram(
            mermaid_path=mermaid_path,
            output_path=svg_path,
        )
        rendered_png = render_diagram(
            mermaid_path=mermaid_path,
            output_path=png_path,
            scale=args.png_scale,
        )
    except subprocess.CalledProcessError as error:
        print(
            "Mermaid file saved, but diagram rendering failed via mmdc: "
            f"{error}",
            file=sys.stderr,
        )
        return 1

    if rendered_svg or rendered_png:
        print(f"Generated Mermaid: {mermaid_path}")
        if rendered_svg:
            print(f"Generated SVG: {svg_path}")
        if rendered_png:
            print(f"Generated PNG: {png_path}")
        return 0

    print(f"Generated Mermaid: {mermaid_path}")
    print("SVG and PNG were not generated because `mmdc` is not installed.")
    print("Install Mermaid CLI and rerun:")
    print("  npm install -g @mermaid-js/mermaid-cli")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
