from deepagents import create_deep_agent

from contracts.task_request import InputStatus, TaskRequest
from contracts.task_response import TaskResponse
from settings.supervisor import (
    SPECIALIST_SUBAGENTS,
    SUPERVISOR_AGENT_NAME,
    SUPERVISOR_SYSTEM_PROMPT,
    get_openai_model,
)
from utils.supervisor import (
    parse_planned_supervisor_output,
    read_last_message_text,
    sort_plan_steps,
)


def create_supervisor_agent(model: str | None = None):
    return create_deep_agent(
        model=get_openai_model(explicit_model=model),
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        subagents=SPECIALIST_SUBAGENTS,
        name=SUPERVISOR_AGENT_NAME,
    )


def run_supervisor_agent(
    task_request: TaskRequest, model: str | None = None
) -> TaskResponse:
    if task_request.input_status == InputStatus.NEEDS_CLARIFICATION:
        return TaskResponse.from_clarification_request(task_request=task_request)

    selected_model = get_openai_model(explicit_model=model)
    agent = create_supervisor_agent(model=selected_model)
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": task_request.to_prompt(),
                }
            ]
        }
    )
    planned_output = parse_planned_supervisor_output(
        raw_text=read_last_message_text(result=result)
    )
    return TaskResponse.from_planned_task(
        task_request=task_request,
        model=selected_model,
        plan=sort_plan_steps(planned_output.plan),
        confidence=planned_output.confidence,
        risk_flags=planned_output.risk_flags,
        requires_user_approval=planned_output.requires_user_approval,
    )
