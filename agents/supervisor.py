import os

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
from utils.workflow_logging import get_application_logger, log_ai_request
from utils.workflow_delegation import delegate_workflow_plan
from utils.workflow_plan_builder import build_workflow_plan
from utils.workflow_risk import assess_workflow_risk, build_workflow_confidence

logger = get_application_logger("agents.supervisor")


def create_supervisor_agent(model: str | None = None):
    return create_deep_agent(
        model=get_openai_model(explicit_model=model),
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        subagents=SPECIALIST_SUBAGENTS,
        name=SUPERVISOR_AGENT_NAME,
    )


def run_supervisor_agent(
    task_request: TaskRequest,
    model: str | None = None,
    execution_mode: str = "parallel",
) -> TaskResponse:
    if task_request.input_status == InputStatus.NEEDS_CLARIFICATION:
        return TaskResponse.from_clarification_request(task_request=task_request)

    selected_model = get_openai_model(explicit_model=model)
    planned_output = run_supervisor_planning(
        task_request=task_request,
        model=selected_model,
    )
    risk_assessment = assess_workflow_risk(task_request)
    plan = sort_plan_steps(planned_output["plan"])
    delegation_result = delegate_workflow_plan(
        plan=plan,
        task_request=task_request,
        model=selected_model,
        execution_mode=execution_mode,
    )
    response = TaskResponse.from_planned_task(
        task_request=task_request,
        model=selected_model,
        plan=delegation_result["plan"],
        confidence=planned_output["confidence"],
        risk_flags=planned_output["risk_flags"] or risk_assessment.risk_flags,
        requires_user_approval=planned_output["requires_user_approval"],
        delegation_result=delegation_result,
    )
    return response


def run_supervisor_planning(task_request: TaskRequest, model: str) -> dict:
    if not os.getenv("OPENAI_API_KEY"):
        return build_fallback_planning_result(task_request)

    prompt = task_request.to_prompt()
    log_ai_request(
        logger,
        request_id=task_request.request_id,
        model=model,
        prompt=prompt,
    )
    agent = create_supervisor_agent(model=model)
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ]
        }
    )

    raw_text = read_last_message_text(result=result)
    try:
        planned_output = parse_planned_supervisor_output(raw_text=raw_text)
    except Exception:
        return build_fallback_planning_result(task_request)
    return {
        "plan": planned_output.plan,
        "confidence": planned_output.confidence,
        "risk_flags": planned_output.risk_flags,
        "requires_user_approval": planned_output.requires_user_approval,
    }


def build_fallback_planning_result(task_request: TaskRequest) -> dict:
    risk_assessment = assess_workflow_risk(task_request)
    return {
        "plan": build_workflow_plan(task_request),
        "confidence": build_workflow_confidence(task_request),
        "risk_flags": risk_assessment.risk_flags,
        "requires_user_approval": risk_assessment.requires_user_approval,
    }
