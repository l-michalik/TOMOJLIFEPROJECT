from pydantic import BaseModel


class TaskResponse(BaseModel):
    request_id: str
    model: str
    answer: str

