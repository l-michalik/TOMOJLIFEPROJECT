# TOMOJLIFEPROJECT

This project contains a basic `Supervisor` API backed by `deepagents`. It accepts a DevOps task request and returns a simple plan, delegation to specialist agents, and identified risks.

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
    "task_description": "Deploy billing-api to the stage environment",
    "parameters": {},
    "context": {
      "environment": "stage",
      "priority": "medium",
      "ticket_id": "OPS-123",
      "conversation_id": ""
    }
  }'
```

## Structure

- `api/app.py` - FastAPI application and routes
- `contracts/task_context.py` - task context contract
- `contracts/task_request.py` - task input contract
- `contracts/task_response.py` - task response contract
- `agents/supervisor.py` - deepagents-based supervisor logic
- `prompts/` - Markdown prompts for the supervisor and specialist subagents
