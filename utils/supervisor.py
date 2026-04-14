from json import loads

from contracts.task_response import PlannedSupervisorOutput, WorkflowPlanStep


def read_last_message_text(result: dict) -> str:
    messages = result.get("messages", [])
    if not messages:
        return ""

    last_message = messages[-1]
    content = getattr(last_message, "content", "")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))
        return "\n".join(part for part in text_parts if part)

    return str(content)


def parse_planned_supervisor_output(raw_text: str) -> PlannedSupervisorOutput:
    return PlannedSupervisorOutput.model_validate(loads(raw_text))


def sort_plan_steps(plan: list[WorkflowPlanStep]) -> list[WorkflowPlanStep]:
    return sorted(plan, key=lambda step: step.step_order)
