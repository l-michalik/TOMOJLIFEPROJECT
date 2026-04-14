from enum import Enum

from pydantic import BaseModel


class ApprovalDecisionStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class WorkflowApprovalDecisionRequest(BaseModel):
    approved: bool
    decision_by: str
    decision_reason: str | None = None

    def to_status(self) -> ApprovalDecisionStatus:
        if self.approved:
            return ApprovalDecisionStatus.APPROVED
        return ApprovalDecisionStatus.REJECTED
