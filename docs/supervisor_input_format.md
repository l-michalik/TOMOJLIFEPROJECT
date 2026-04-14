# Docelowy format wejścia Supervisora

Ten dokument opisuje zunifikowany kontrakt wejściowy Supervisora zgodny ze specyfikacją systemu z [project_specification.MD](./project_specification.MD).

## Cel kontraktu

Kontrakt wejściowy:

- normalizuje zgłoszenia z Jira, chatu i API do jednego formatu,
- rozdziela treść zgłoszenia od parametrów wykonania,
- buduje ustandaryzowany obiekt roboczy na podstawie treści zgłoszenia i parametrów integracyjnych,
- pozwala odróżnić błąd schematu od zgłoszenia wymagającego doprecyzowania,
- daje Supervisorowi komplet danych potrzebnych do walidacji, audytu i planowania.

## Struktura danych

```json
{
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
      "service_name": "billing-api",
      "release_version": "2026.04.14"
    }
  }
}
```

## Opis pól

- `request_id`: globalny identyfikator zgłoszenia używany do trace i audytu.
- `source`: kanał wejściowy. Dozwolone wartości: `jira`, `chat`, `api`.
- `user_id`: identyfikator użytkownika lub systemu inicjującego zgłoszenie.
- `user_request`: opis celu biznesowego lub operacyjnego przekazany do Supervisora.
- `params.target_environment`: środowisko docelowe. Dozwolone wartości: `dev`, `stage`, `prod`.
- `params.priority`: priorytet zgłoszenia. Dozwolone wartości: `low`, `medium`, `high`.
- `params.ticket_id`: identyfikator zgłoszenia źródłowego w Jira.
- `params.conversation_id`: identyfikator konwersacji źródłowej dla kanału chat.
- `params.execution_options`: dodatkowe parametry wykonania przekazywane dalej do planowania i agentów specjalistycznych.

## Zasady walidacji

Walidacja jest podzielona na dwa poziomy.

### 1. Walidacja schematu

Na poziomie schematu system wymaga poprawnej struktury JSON oraz poprawnych wartości enumów:

- `source` musi należeć do `jira|chat|api`,
- `params.target_environment` musi należeć do `dev|stage|prod`, jeśli zostało przekazane,
- `params.priority` musi należeć do `low|medium|high`, jeśli zostało przekazane,
- `params.execution_options` musi być obiektem.

Naruszenie tych zasad kończy request błędem walidacji modelu.

### 2. Walidacja kompletności przed planowaniem

Jeżeli struktura jest poprawna, Supervisor ocenia kompletność danych potrzebnych do planowania. Brak danych nie kończy requestu błędem technicznym, tylko ustawia status:

- `ready_for_planning` gdy dane są kompletne,
- `needs_clarification` gdy brakuje informacji koniecznych do planowania.

Za wymagające doprecyzowania uznawane są następujące przypadki:

- brak `request_id`,
- brak `user_id`,
- brak `user_request`,
- brak `standardized_work_item.target_environment`,
- brak `params.priority`,
- brak `standardized_work_item.service_name`,
- brak `standardized_work_item.operation_type`,
- `source=jira` bez `params.ticket_id`,
- `source=chat` bez `params.conversation_id`.

## Ustandaryzowany obiekt roboczy

Na etapie wejściowym Supervisor buduje dodatkowy obiekt `standardized_work_item`, który trafia do `normalized_request` i stanowi podstawę do dalszego planowania.

```json
{
  "service_name": "billing-api",
  "target_environment": "stage",
  "operation_type": "deploy",
  "execution_parameters": {
    "service_name": "billing-api",
    "target_environment": "stage",
    "release_version": "2026.04.14"
  },
  "constraints": ["no_downtime"]
}
```

Zasady budowy:

- `service_name` jest pobierane najpierw z `params.execution_options`, a jeśli go tam nie ma, z treści `user_request`,
- `target_environment` jest pobierane z `params.target_environment`, z parametrów integracyjnych albo z treści zgłoszenia,
- `operation_type` jest określane na podstawie słów kluczowych w zgłoszeniu lub jawnego parametru operacji,
- `execution_parameters` zawiera znormalizowane parametry wykonania przekazane przez integrację i parametry wywnioskowane z treści,
- `constraints` zawiera ograniczenia jawnie przekazane przez integrację lub rozpoznane w treści zgłoszenia.

## Obsługa braków danych

Jeżeli request jest niekompletny, Supervisor:

- nie uruchamia planowania,
- nie deleguje zadań do agentów specjalistycznych,
- zwraca `status: "needs_clarification"`,
- zwraca listę `validation_errors` z polami wymagającymi uzupełnienia,
- zachowuje `normalized_request`, żeby źródłowy kanał mógł wznowić zgłoszenie po uzupełnieniu danych.

Przykładowa odpowiedź:

```json
{
  "request_id": "req-002",
  "status": "needs_clarification",
  "validation_errors": [
    {
      "field_name": "standardized_work_item.target_environment",
      "reason": "Środowisko docelowe musi zostać wskazane w parametrach lub treści zgłoszenia."
    }
  ],
  "normalized_request": {
    "request_id": "req-002",
    "source": "chat",
    "user_id": "alice",
    "user_request": "Deploy billing-api",
    "params": {
      "target_environment": null,
      "priority": "high",
      "ticket_id": null,
      "conversation_id": "conv-42",
      "execution_options": {}
    },
    "standardized_work_item": {
      "service_name": "billing-api",
      "target_environment": null,
      "operation_type": "deploy",
      "execution_parameters": {
        "service_name": "billing-api"
      },
      "constraints": []
    },
    "clarification_items": [
      {
        "field_name": "standardized_work_item.target_environment",
        "reason": "Środowisko docelowe musi zostać wskazane w parametrach lub treści zgłoszenia."
      }
    ],
    "input_status": "needs_clarification"
  },
  "model": null,
  "answer": "Request requires clarification before planning."
}
```

## Format odpowiedzi po planowaniu

Po poprawnym zakończeniu etapu planowania Supervisor zwraca ustrukturyzowany kontrakt workflow:

```json
{
  "request_id": "req-001",
  "status": "planned",
  "validation_errors": [],
  "normalized_request": {
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
    },
    "standardized_work_item": {
      "service_name": "billing-api",
      "target_environment": "stage",
      "operation_type": "deploy",
      "execution_parameters": {
        "service_name": "billing-api",
        "target_environment": "stage"
      },
      "constraints": []
    },
    "clarification_items": [],
    "input_status": "ready_for_planning"
  },
  "model": "openai:gpt-5.4-mini",
  "plan": [
    {
      "step_id": "STEP-1",
      "owner_agent": "DeploymentAgent",
      "task_type": "deployment_analysis",
      "task_description": "Prepare deployment rollout for billing-api on stage.",
      "agent_instruction": "Review deployment prerequisites and return only JSON.",
      "step_order": 1,
      "depends_on": [],
      "expected_output_json_format": {
        "focus": "deployment",
        "summary": "string",
        "findings": ["string"],
        "proposed_actions": [
          {
            "action_id": "string",
            "action_type": "string",
            "details": {}
          }
        ],
        "risks": ["string"],
        "artifacts": ["string"]
      },
      "start_conditions": [
        "Request input is validated and ready for planning."
      ],
      "result_handoff_condition": "Forward the result when deployment prerequisites and proposed actions are returned in JSON.",
      "required_input_context": {
        "target_environment": "stage",
        "service_name": "billing-api"
      },
      "expected_result": "Deployment plan is ready for technical validation.",
      "status": "planned",
      "risk_flags": [],
      "requires_user_approval": false
    }
  ],
  "state": {
    "request_id": "req-001",
    "source": "jira",
    "workflow_id": "workflow-req-001",
    "current_stage": "delegation",
    "lifecycle_status": "planned",
    "plan_steps": [
      {
        "step_id": "STEP-1",
        "step_order": 1,
        "owner_agent": "DeploymentAgent",
        "task_description": "Prepare deployment rollout for billing-api on stage.",
        "status": "planned",
        "depends_on": [],
        "updated_at": "2026-04-14T10:00:00Z"
      }
    ],
    "decision_history": [
      {
        "decision_id": "DEC-1",
        "decision_type": "state_transition",
        "summary": "Request received by Supervisor.",
        "actor": "Supervisor",
        "related_step_id": null,
        "previous_status": null,
        "new_status": "received",
        "created_at": "2026-04-14T10:00:00Z"
      },
      {
        "decision_id": "DEC-2",
        "decision_type": "plan_created",
        "summary": "Workflow plan created and stored in state.",
        "actor": "Supervisor",
        "related_step_id": null,
        "previous_status": "received",
        "new_status": "planned",
        "created_at": "2026-04-14T10:00:00Z"
      }
    ],
    "resume_data": {
      "checkpoint_id": "req-001:checkpoint:planning",
      "resume_token": "req-001:resume:planning",
      "last_completed_step_id": null,
      "next_step_id": "STEP-1",
      "delegated_step_ids": [],
      "waiting_step_ids": []
    },
    "timestamps": {
      "received_at": "2026-04-14T10:00:00Z",
      "updated_at": "2026-04-14T10:00:00Z",
      "clarification_requested_at": null,
      "planned_at": "2026-04-14T10:00:00Z",
      "delegated_at": null,
      "waiting_for_results_at": null,
      "waiting_for_approval_at": null,
      "executing_at": null,
      "completed_at": null,
      "failed_at": null,
      "blocked_at": null
    }
  },
  "confidence": 0.92,
  "risk_flags": [],
  "requires_user_approval": false,
  "answer": null
}
```

Znaczenie dodatkowych pól:

- `plan[*].step_order`: kolejność wykonania kroków w workflow.
- `plan[*].task_type`: jawna klasyfikacja kroku przekazywana dalej do ustandaryzowanego kontraktu wejściowego agenta.
- `plan[*].agent_instruction`: instrukcja przekazywana do docelowego agenta dla danego kroku.
- `plan[*].expected_output_json_format`: oczekiwany format odpowiedzi JSON zwracanej przez agenta.
- `plan[*].start_conditions`: warunki rozpoczęcia kroku.
- `plan[*].result_handoff_condition`: warunek przekazania wyniku kroku do agregacji.
- `plan[*].required_input_context`: kontekst wejściowy wymagany przez agenta odpowiedzialnego za krok.
- `plan[*].expected_result`: oczekiwany rezultat kroku przekazywany dalej do agregacji.
- `plan[*].status`: status kroku na końcu etapu planowania.
- `state.lifecycle_status`: aktualny status lifecycle zadania. Obsługiwane wartości to `received`, `needs_clarification`, `planned`, `delegated`, `waiting_for_results`, `waiting_for_approval`, `executing`, `completed`, `failed`, `blocked`.
- `state.plan_steps`: runtime'owa lista kroków wraz z bieżącym statusem każdego kroku.
- `state.decision_history`: historia decyzji i przejść stanu wykonywana przez Supervisora.
- `state.resume_data`: dane potrzebne do wznowienia workflow od zapisanego checkpointu.
- `state.timestamps`: znaczniki czasu dla kluczowych etapów lifecycle zadania.
- `confidence`: ocena pewności planu zwrócona przez Supervisora.
- `risk_flags`: zagregowane flagi ryzyka dla całego workflow.
- `requires_user_approval`: informacja, czy workflow powinien zatrzymać się na bramce akceptacji użytkownika.

## Zgodność wsteczna

API nadal akceptuje dotychczasowy format:

- `task_description` jest mapowane do `user_request`,
- `parameters` oraz `context` są mapowane do `params`.

To pozwala przejść do nowego kontraktu bez natychmiastowego łamania istniejących integracji.
