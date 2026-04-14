from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from agents.supervisor import resume_supervisor_workflow, run_supervisor_agent
from contracts.task_request import TaskRequest
from contracts.task_response import TaskResponse
from contracts.workflow_approval import WorkflowApprovalDecisionRequest
from utils.workflow_logging import configure_application_logging

load_dotenv()
configure_application_logging()

app = FastAPI(title="TOMOJLIFEPROJECT API")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/tasks", response_model=TaskResponse)
def handle_task(task_request: TaskRequest) -> TaskResponse:
    return run_supervisor_agent(task_request=task_request)


@app.post("/api/tasks/{request_id}/approval", response_model=TaskResponse)
def handle_task_approval(
    request_id: str,
    approval_request: WorkflowApprovalDecisionRequest,
) -> TaskResponse:
    try:
        return resume_supervisor_workflow(
            request_id=request_id,
            approval_request=approval_request,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
