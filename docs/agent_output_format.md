# Ustandaryzowany format wyjścia agentów wykonawczych

Ten dokument definiuje wspólny kontrakt wyjściowy agentów specjalistycznych i wykonawczych zgodny ze specyfikacją z [project_specification.MD](./project_specification.MD). Kontrakt jest wspólny dla `DeploymentAgent`, `InfraAgent`, `CI_CD_Agent`, `Risk/Policy Agent`, `Human Review Interface` oraz `Execution Agent`.

## Cel kontraktu

Kontrakt wyjściowy:

- wymusza jeden format odpowiedzi zwracanej do `Supervisor`,
- oddziela wynik merytoryczny od informacji potrzebnych do audytu i orkiestracji,
- dostarcza dane do agregacji kroków workflow bez dodatkowego mapowania domenowego,
- przenosi logi, ostrzeżenia, błędy techniczne i artefakty w jawnej, wersjonowalnej strukturze,
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
  }
}
```

## Pola obowiązkowe

- `result`: wynik merytoryczny kroku zgodny z `expected_output_json_format`.
- `logs`: lista krótkich logów operacyjnych opisujących przebieg kroku.
- `status`: końcowy status kroku używany przez `Supervisor` do sterowania workflow.

## Pola wymagane przez specyfikację orkiestracji

- `analysis_details`: uporządkowane szczegóły wykonanych analiz.
- `recommended_actions`: lista rekomendowanych lub przygotowanych akcji do dalszego przetwarzania.
- `artifacts`: lista artefaktów wytworzonych albo zidentyfikowanych przez agenta.
- `warnings`: ostrzeżenia nieblokujące kroku, ale istotne dla operatora lub Supervisora.
- `technical_errors`: błędy techniczne i wykonawcze.
- `supervisor_data`: dane pomocnicze do agregacji wyników przez `Supervisor`.

## Opis pól rozszerzonych

- `analysis_details[].category`: obszar analizy, np. `deployment`, `infra`, `ci_cd`, `policy`.
- `analysis_details[].summary`: krótki opis wyniku analizy.
- `analysis_details[].details`: szczegóły domenowe, np. listy findings, metadane, decyzje.
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
- `technical_errors[].details`: surowe dane diagnostyczne potrzebne do debugowania.
- `supervisor_data.produced_action_ids`: akcje przygotowane przez krok i gotowe do agregacji.
- `supervisor_data.blocked_action_ids`: akcje zablokowane przez politykę, brak zależności albo inne ograniczenie.
- `supervisor_data.approval_required_action_ids`: akcje, które wymagają decyzji człowieka.
- `supervisor_data.next_decision`: następna decyzja workflow oczekiwana przez Supervisora.
- `supervisor_data.handoff_payload`: dodatkowy payload przekazywany do kolejnego etapu, zwykle do `Execution Agent`.

## Dozwolone statusy i znaczenie workflow

- `completed`: krok zakończył się poprawnie, a `Supervisor` może kontynuować zależne kroki.
- `failed`: krok zakończył się błędem technicznym lub semantycznym i `Supervisor` powinien oznaczyć krok jako nieudany.
- `blocked`: krok nie może być kontynuowany z powodu brakujących zależności, ograniczeń polityki albo brakującego kontekstu.
- `waiting_for_approval`: krok wymaga decyzji człowieka przed dalszą kontynuacją workflow.

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

- docelowy format top-level z polami `analysis_details`, `recommended_actions`, `artifacts`, `warnings`, `technical_errors` i `supervisor_data`,
- zgodność wsteczna z payloadem legacy, w którym część tych danych znajduje się wewnątrz `result`, np. `proposed_actions`, `artifacts`, `warnings`, `decisions` albo `execution_handoff`.

Jeżeli agent zwróci tylko format legacy, warstwa kontraktu znormalizuje odpowiedź do wspólnego modelu. Jeżeli agent zwróci pełny format docelowy, `Supervisor` użyje go bez utraty danych do agregacji.
