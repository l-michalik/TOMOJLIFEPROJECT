# Ustandaryzowany format wyjścia agentów wykonawczych

Ten dokument definiuje wspólny kontrakt wyjściowy agentów specjalistycznych i wykonawczych zgodny ze specyfikacją z [project_specification.MD](./project_specification.MD). Kontrakt jest wspólny dla `DeploymentAgent`, `InfraAgent`, `CI_CD_Agent`, `Risk/Policy Agent`, `Human Review Interface` oraz `Execution Agent`.

## Cel kontraktu

Kontrakt wyjściowy:

- wymusza jeden format odpowiedzi zwracanej do `Supervisor`,
- oddziela wynik merytoryczny od informacji potrzebnych do audytu i orkiestracji,
- dostarcza dane do agregacji kroków workflow bez dodatkowego mapowania domenowego,
- przenosi logi, ostrzeżenia, błędy techniczne i artefakty w jawnej, wersjonowalnej strukturze,
- materializuje krótkoterminową pamięć sesyjną agenta dla pojedynczego kroku bez tworzenia nowego źródła prawdy,
- jednoznacznie określa status kroku i jego wpływ na dalszy workflow.

## Struktura danych

```json
{
  "result": {
    "focus": "deployment",
    "summary": "Deployment analysis completed.",
    "findings": [
      "Release version is available in the registry."
    ],
    "proposed_actions": [
      {
        "action_id": "STEP-1-ACTION-1",
        "action_type": "deploy",
        "details": {
          "service_name": "billing-api",
          "target_environment": "stage"
        }
      }
    ],
    "artifacts": [
      "s3://artifacts/release-notes.md"
    ]
  },
  "logs": [
    "Deployment prerequisites analyzed."
  ],
  "status": "completed",
  "execution_details": {
    "owner_agent": "DeploymentAgent",
    "request_id": "req-001",
    "step_id": "STEP-1",
    "user_id": "user-123",
    "started_at": "2026-04-15T10:00:00Z",
    "completed_at": "2026-04-15T10:00:03Z",
    "input_snapshot": {
      "instruction": "Analyze deployment prerequisites."
    },
    "final_status": "completed",
    "audit_events": [
      {
        "event_id": "STEP-1-event-1",
        "timestamp": "2026-04-15T10:00:00Z",
        "owner_agent": "DeploymentAgent",
        "request_id": "req-001",
        "step_id": "STEP-1",
        "user_id": "user-123",
        "event_type": "input_received",
        "status": null,
        "summary": "Specialist agent received normalized working input.",
        "payload": {
          "working_input": {
            "instruction": "Analyze deployment prerequisites."
          }
        }
      }
    ],
    "tool_calls": []
  },
  "analysis_details": [
    {
      "category": "deployment",
      "summary": "All rollout prerequisites are available.",
      "details": {
        "findings": [
          "Release version is available in the registry."
        ]
      }
    }
  ],
  "recommended_actions": [
    {
      "action_id": "STEP-1-ACTION-1",
      "action_type": "deploy",
      "description": "Deploy billing-api to stage.",
      "details": {
        "service_name": "billing-api",
        "target_environment": "stage"
      }
    }
  ],
  "artifacts": [
    {
      "name": "release-notes",
      "artifact_type": "document",
      "uri": "s3://artifacts/release-notes.md",
      "description": "Generated release notes."
    }
  ],
  "warnings": [],
  "technical_errors": [],
  "supervisor_data": {
    "produced_action_ids": [
      "STEP-1-ACTION-1"
    ],
    "blocked_action_ids": [],
    "approval_required_action_ids": [],
    "next_decision": null,
    "handoff_payload": {}
  },
  "session_memory": {
    "request_id": "req-001",
    "step_id": "STEP-1",
    "owner_agent": "DeploymentAgent",
    "authority": {
      "authoritative_source": "supervisor_workflow_state",
      "scope": "single_step_execution",
      "is_source_of_truth": false,
      "usage_rule": "Use this memory only as a local session snapshot. Resolve conflicts in favor of Supervisor-managed global workflow state."
    },
    "current_task_context": {
      "task_description": "Analyze deployment prerequisites.",
      "service_name": "billing-api",
      "target_environment": "stage"
    },
    "recent_commands": [],
    "intermediate_results": [],
    "environment_logs": [
      "Deployment prerequisites analyzed."
    ],
    "technical_notes": {
      "risk_flags": []
    },
    "updated_at": "2026-04-15T10:00:00Z"
  }
}
```

## Pola obowiązkowe

- `result`: wynik merytoryczny kroku zgodny z `expected_output_json_format`.
- `logs`: lista krótkich logów operacyjnych opisujących przebieg kroku.
- `status`: końcowy status kroku używany przez `Supervisor` do sterowania workflow.
- `execution_details`: ustandaryzowany audit trail zawierający wejście robocze, decyzje, wywołania narzędzi, odpowiedzi narzędzi oraz finalny status kroku.

## Pola wymagane przez specyfikację orkiestracji

- `analysis_details`: uporządkowane szczegóły wykonanych analiz.
- `recommended_actions`: lista rekomendowanych lub przygotowanych akcji do dalszego przetwarzania.
- `artifacts`: lista artefaktów wytworzonych albo zidentyfikowanych przez agenta.
- `warnings`: ostrzeżenia nieblokujące kroku, ale istotne dla operatora lub Supervisora.
- `technical_errors`: błędy techniczne i wykonawcze.
- `supervisor_data`: dane pomocnicze do agregacji wyników przez `Supervisor`.
- `session_memory`: krótkoterminowa pamięć sesyjna agenta dla bieżącego kroku.
- `execution_details.audit_events`: strukturalne zdarzenia audytowe gotowe do agregacji, tracingu i audytu.
- `execution_details.tool_calls`: strukturalny zapis request/response/error dla narzędzi użytych przez agenta.

## Opis pól rozszerzonych

- `analysis_details[].category`: obszar analizy, np. `deployment`, `infra`, `ci_cd`, `policy`.
- `analysis_details[].summary`: krótki opis wyniku analizy.
- `analysis_details[].details`: szczegóły domenowe, np. listy findings, metadane, decyzje.
- `execution_details.owner_agent`: agent, który wygenerował audit trail.
- `execution_details.request_id`: identyfikator korelacyjny zgłoszenia.
- `execution_details.step_id`: identyfikator kroku workflow.
- `execution_details.user_id`: identyfikator użytkownika powiązanego ze zgłoszeniem.
- `execution_details.input_snapshot`: znormalizowane wejście robocze po sanitizacji danych wrażliwych.
- `execution_details.final_status`: status końcowy kroku zapisany w audit trail.
- `execution_details.audit_events[]`: uporządkowane zdarzenia typu `input_received`, `decision_recorded`, `tool_call_started`, `tool_call_completed`, `tool_call_failed`, `error_recorded`.
- `execution_details.tool_calls[]`: pełniejszy zapis request/response/error dla pojedynczego wywołania narzędzia.
- `recommended_actions[].action_id`: stabilny identyfikator akcji w obrębie workflow.
- `recommended_actions[].action_type`: typ akcji, np. `deploy`, `terraform_apply`, `pipeline_run`.
- `recommended_actions[].description`: zwięzły opis celu akcji.
- `recommended_actions[].details`: parametry potrzebne do dalszego review lub wykonania.
- `artifacts[].name`: nazwa artefaktu.
- `artifacts[].artifact_type`: typ artefaktu, np. `document`, `log`, `plan`, `report`, `reference`.
- `artifacts[].uri`: ścieżka lub URI do artefaktu.
- `artifacts[].description`: opis znaczenia artefaktu.
- `technical_errors[].message`: czytelny opis błędu.
- `technical_errors[].code`: techniczny kod błędu do śledzenia i automatyzacji.
- `technical_errors[].category`: kategoria problemu, np. `prompt_error`, `tool_invocation_error`, `timeout`, `empty_result`, `response_inconsistency`.
- `technical_errors[].supervisor_recommendation`: jawna rekomendacja dla `Supervisor`, czy wykonać `retry`, `escalate` albo `mark_failed`.
- `technical_errors[].details`: surowe dane diagnostyczne potrzebne do debugowania.
- `supervisor_data.produced_action_ids`: akcje przygotowane przez krok i gotowe do agregacji.
- `supervisor_data.blocked_action_ids`: akcje zablokowane przez politykę, brak zależności albo inne ograniczenie.
- `supervisor_data.approval_required_action_ids`: akcje, które wymagają decyzji człowieka.
- `supervisor_data.next_decision`: następna decyzja workflow oczekiwana przez Supervisora.
- `supervisor_data.handoff_payload`: dodatkowy payload przekazywany do kolejnego etapu, zwykle do `Execution Agent`.
- `session_memory.authority`: jawna deklaracja, że pamięć lokalna jest podrzędna wobec globalnego stanu workflow.
- `session_memory.current_task_context`: aktualny kontekst bieżącego kroku potrzebny podczas wykonania.
- `session_memory.recent_commands`: ostatnie komendy lub wywołania narzędzi wykryte w lokalnym kontekście sesji.
- `session_memory.intermediate_results`: skrócone wyniki pośrednie z zależności i bieżącego kroku.
- `session_memory.environment_logs`: lokalny wycinek logów środowiskowych istotnych dla pojedynczego kroku.
- `session_memory.technical_notes`: techniczne dane pomocnicze, np. wejście runtime, flagi ryzyka i ostatnie szczegóły wykonania.

## Dozwolone statusy i znaczenie workflow

- `completed`: krok zakończył się poprawnie, a `Supervisor` może kontynuować zależne kroki.
- `failed`: krok zakończył się błędem technicznym lub semantycznym i `Supervisor` powinien oznaczyć krok jako nieudany.
- `blocked`: krok nie może być kontynuowany z powodu brakujących zależności, ograniczeń polityki albo brakującego kontekstu.
- `waiting_for_approval`: krok wymaga decyzji człowieka przed dalszą kontynuacją workflow.

## Zasady obsługi błędów agentów

- Każdy agent musi zwrócić kompletny kontrakt nawet wtedy, gdy wystąpi błąd promptowania, błąd narzędzia, timeout, pusty wynik albo niespójna odpowiedź.
- Błędy techniczne muszą zawierać co najmniej `message` oraz przynajmniej jedno z pól `code` lub `category`.
- Dla odpowiedzi błędnych albo niespójnych agent musi ustawić `technical_errors[].supervisor_recommendation`, aby `Supervisor` mógł automatycznie podjąć decyzję `retry`, `escalate` albo `mark_failed`.
- Status `completed` nie może być użyty z pustym `result` ani z payloadem niespełniającym `expected_output_json_format`; takie odpowiedzi są normalizowane do `failed`.

## Zasady mapowania na workflow Supervisora

- `completed` mapuje się na `WorkflowStepStatus.COMPLETED`.
- `failed` mapuje się na `WorkflowStepStatus.FAILED`.
- `blocked` mapuje się na `WorkflowStepStatus.BLOCKED`.
- `waiting_for_approval` mapuje się na `WorkflowStepStatus.WAITING_FOR_APPROVAL`.

Wpływ na dalszy przebieg:

- co najmniej jeden krok ze statusem `failed` przełącza workflow do stanu wymagającego review błędów,
- co najmniej jeden krok ze statusem `waiting_for_approval` zatrzymuje workflow na bramce human approval,
- krok `blocked` blokuje zależne kroki i wymaga uzupełnienia kontekstu albo decyzji operatora,
- tylko `completed` pozwala odblokować kroki zależne.

## Zasady kompatybilności

Model `AgentExecutionOutput` wspiera dwa poziomy zgodności:

- docelowy format top-level z polami `analysis_details`, `recommended_actions`, `artifacts`, `warnings`, `technical_errors`, `supervisor_data` i `session_memory`,
- zgodność wsteczna z payloadem legacy, w którym część tych danych znajduje się wewnątrz `result`, np. `proposed_actions`, `artifacts`, `warnings`, `decisions` albo `execution_handoff`.

Jeżeli agent zwróci tylko format legacy, warstwa kontraktu znormalizuje odpowiedź do wspólnego modelu. Jeżeli agent zwróci pełny format docelowy, `Supervisor` użyje go bez utraty danych do agregacji.

## Zasada źródła prawdy

- `session_memory` nie jest trwałym ani nadrzędnym stanem workflow.
- Pamięć sesyjna jest budowana z danych wejściowych kroku, wyników zależności oraz bieżącej odpowiedzi agenta.
- W razie rozbieżności zawsze obowiązuje stan globalny utrzymywany przez `Supervisor` w `WorkflowState` i checkpointach.
