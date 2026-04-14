from pydantic import BaseModel


class TaskContext(BaseModel):
    environment: str = "dev"
    priority: str = "medium"
    ticket_id: str = ""
    conversation_id: str = ""
