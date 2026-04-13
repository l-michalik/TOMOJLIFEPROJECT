from __future__ import annotations

from typing import Final, Literal, NotRequired, TypedDict, TypeAlias, get_args


SubmissionSource: TypeAlias = Literal["jira", "chat", "api"]
RequesterRole: TypeAlias = Literal["admin", "devops", "platform-engineer", "viewer"]
ExecutionEnvironment: TypeAlias = Literal["dev", "stage", "prod"]
TaskOperation: TypeAlias = Literal[
    "deploy",
    "configure",
    "diagnose",
    "restart",
    "rollback",
    "provision",
]

SUBMISSION_SOURCES: Final[tuple[SubmissionSource, ...]] = get_args(SubmissionSource)
REQUESTER_ROLES: Final[tuple[RequesterRole, ...]] = get_args(RequesterRole)
EXECUTION_ENVIRONMENTS: Final[tuple[ExecutionEnvironment, ...]] = get_args(ExecutionEnvironment)
TASK_OPERATIONS: Final[tuple[TaskOperation, ...]] = get_args(TaskOperation)


class Requester(TypedDict):
    id: str
    role: NotRequired[RequesterRole]
    displayName: NotRequired[str]


class TaskParameters(TypedDict, total=False):
    environment: ExecutionEnvironment
    serviceName: str
    operation: TaskOperation
    targetVersion: str
    dryRun: bool
    approvalRequired: bool
    timeoutSeconds: int
    tags: list[str]


class SubmissionMetadata(TypedDict, total=False):
    ticketId: str
    threadId: str
    correlationId: str


class TaskSubmission(TypedDict):
    taskDescription: str
    source: SubmissionSource
    requester: Requester
    parameters: TaskParameters
    metadata: SubmissionMetadata


class SupervisorContext(TypedDict):
    source: SubmissionSource
    requester: Requester
    metadata: SubmissionMetadata
    schemaVersion: str


class SupervisorInput(TypedDict):
    user_request: str
    params: TaskParameters
    context: SupervisorContext
