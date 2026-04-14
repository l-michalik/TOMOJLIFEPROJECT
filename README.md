# TOMOJLIFEPROJECT

This project contains a basic `Supervisor` API backed by `deepagents`. It accepts a normalized DevOps task request, parses the incoming description into a standardized work item, validates completeness before planning, and returns either a clarification request or a structured planning contract with workflow state, plan steps, confidence, and risk metadata.

## Requirements

- Python `3.13`
- `uv`
- `OPENAI_API_KEY`

## Installation

```bash
uv sync
```

## Environment variables

The application loads variables from `.env` with `python-dotenv`.

Example:

```env
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=openai:gpt-5.4-mini
```

The default model is `openai:gpt-5.4-mini`.

## Run the API

Start the API server:

```bash
uv run uvicorn api.app:app --reload
```

Healthcheck:

```bash
curl http://127.0.0.1:8000/health
```

Basic request:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "req-001",
    "source": "jira",
    "user_id": "platform-engineer",
    "user_request": "Deploy billing-api to the stage environment",
    "params": {
      "target_environment": "stage",
      "priority": "medium",
      "ticket_id": "OPS-123",
      "conversation_id": null,
      "execution_options": {
        "service_name": "billing-api"
      }
    }
  }'
```

If required planning data is missing, the API returns `status: "needs_clarification"` with `validation_errors` that describe which fields must be completed before workflow planning can start. Completeness is checked both on transport fields and on the parsed `standardized_work_item`, which extracts `service_name`, `target_environment`, `operation_type`, `execution_parameters`, and `constraints` from the incoming request.

If planning succeeds, the API returns `status: "planned"` and a contract that includes:

- `plan`: ordered workflow steps with assigned specialist agent, task description, dependencies, required context, expected result, step status, risk flags, and approval requirement,
- `state`: workflow identifiers and checkpoint/resume metadata needed for persistence and restart,
- `confidence`: supervisor confidence score for the plan,
- `risk_flags`: aggregated workflow-level risk signals,
- `requires_user_approval`: workflow-level approval flag.

Legacy payload fields `task_description`, `parameters`, and `context` are still accepted and mapped to the new contract.

Detailed contract description is available in `docs/supervisor_input_format.md`.

## Structure

- `api/app.py` - FastAPI application and routes
- `contracts/task_request.py` - supervisor input contract and validation rules
- `utils/task_request_parser.py` - parser that converts integration-layer requests into a standardized work item
- `contracts/task_response.py` - supervisor planning and clarification response contract
- `agents/supervisor.py` - deepagents-based supervisor logic
- `settings/` - supervisor configuration, prompts, and model defaults
- `utils/` - helper functions used by the supervisor flow
- `prompts/` - Markdown prompts for the supervisor and specialist subagents
