from dotenv import load_dotenv
from fastapi import FastAPI

from agents.supervisor import run_supervisor_agent
from contracts.task_request import TaskRequest
from contracts.task_response import TaskResponse

load_dotenv()

app = FastAPI(title="TOMOJLIFEPROJECT API")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/tasks", response_model=TaskResponse)
def handle_task(task_request: TaskRequest) -> TaskResponse:
    return run_supervisor_agent(task_request=task_request)
