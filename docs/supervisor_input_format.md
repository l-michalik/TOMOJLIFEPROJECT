# Docelowy format wejścia Supervisora

Ten dokument opisuje zunifikowany kontrakt wejściowy Supervisora zgodny ze specyfikacją systemu z [project_specification.MD](./project_specification.MD).

## Cel kontraktu

Kontrakt wejściowy:

- normalizuje zgłoszenia z Jira, chatu i API do jednego formatu,
- rozdziela treść zgłoszenia od parametrów wykonania,
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
- brak `params.target_environment`,
- brak `params.priority`,
- `source=jira` bez `params.ticket_id`,
- `source=chat` bez `params.conversation_id`.

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
      "field_name": "params.target_environment",
      "reason": "Środowisko docelowe jest wymagane przed planowaniem."
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
    "clarification_items": [
      {
        "field_name": "params.target_environment",
        "reason": "Środowisko docelowe jest wymagane przed planowaniem."
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
    "clarification_items": [],
    "input_status": "ready_for_planning"
  },
  "model": "openai:gpt-5.4-mini",
  "plan": [
    {
      "step_id": "STEP-1",
      "owner_agent": "DeploymentAgent",
      "task_description": "Prepare deployment rollout for billing-api on stage.",
      "step_order": 1,
      "depends_on": [],
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
    "workflow_id": "workflow-req-001",
    "current_stage": "risk_review",
    "workflow_status": "planning_completed",
    "checkpoint_id": "req-001:checkpoint:planning",
    "resume_token": "req-001:resume:planning",
    "last_completed_step_id": null,
    "next_step_id": "STEP-1"
  },
  "confidence": 0.92,
  "risk_flags": [],
  "requires_user_approval": false,
  "answer": null
}
```

Znaczenie dodatkowych pól:

- `plan[*].step_order`: kolejność wykonania kroków w workflow.
- `plan[*].required_input_context`: kontekst wejściowy wymagany przez agenta odpowiedzialnego za krok.
- `plan[*].expected_result`: oczekiwany rezultat kroku przekazywany dalej do agregacji.
- `plan[*].status`: status kroku na końcu etapu planowania.
- `state.workflow_id`: trwały identyfikator workflow.
- `state.checkpoint_id`: identyfikator checkpointu zapisywanego po planowaniu.
- `state.resume_token`: identyfikator potrzebny do wznowienia procesu od zapisanego checkpointu.
- `confidence`: ocena pewności planu zwrócona przez Supervisora.
- `risk_flags`: zagregowane flagi ryzyka dla całego workflow.
- `requires_user_approval`: informacja, czy workflow powinien zatrzymać się na bramce akceptacji użytkownika.

## Zgodność wsteczna

API nadal akceptuje dotychczasowy format:

- `task_description` jest mapowane do `user_request`,
- `parameters` oraz `context` są mapowane do `params`.

To pozwala przejść do nowego kontraktu bez natychmiastowego łamania istniejących integracji.
