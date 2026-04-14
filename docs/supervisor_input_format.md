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

## Zgodność wsteczna

API nadal akceptuje dotychczasowy format:

- `task_description` jest mapowane do `user_request`,
- `parameters` oraz `context` są mapowane do `params`.

To pozwala przejść do nowego kontraktu bez natychmiastowego łamania istniejących integracji.
