# Ustandaryzowany format wejścia agentów wykonawczych

Ten dokument definiuje docelowy kontrakt wejściowy dla agentów wykonawczych i specjalistycznych zgodny ze specyfikacją z [project_specification.MD](./project_specification.MD). Kontrakt jest wspólny dla kroków delegowanych przez `Supervisor` do `DeploymentAgent`, `InfraAgent`, `CI_CD_Agent`, `Risk/Policy Agent`, `Human Review Interface` oraz `Execution Agent`.

## Cel kontraktu

Kontrakt wejściowy agenta:

- wymusza jednolity payload przekazywany do każdego agenta,
- rozdziela instrukcję wykonania od znormalizowanego kontekstu operacyjnego,
- przenosi do agenta identyfikator kroku, typ zadania, środowisko docelowe i dane z poprzednich kroków,
- utrzymuje spójność między planem workflow a danymi wejściowymi używanymi przez agenta,
- waliduje kompletność informacji potrzebnych do bezpiecznego wykonania części planu.

## Struktura danych

```json
{
  "instruction": "Review deployment prerequisites, rollout sequencing, release inputs, and service availability considerations. Return only JSON using the declared step format.",
  "context": {
    "request_id": "req-001",
    "source": "jira",
    "user_id": "platform-engineer",
    "user_request": "Deploy billing-api to the stage environment",
    "priority": "medium",
    "service_name": "billing-api"
  },
  "step_id": "STEP-1",
  "owner_agent": "DeploymentAgent",
  "task_type": "deployment_analysis",
  "target_environment": "stage",
  "technical_params": {
    "request_id": "req-001",
    "source": "jira",
    "priority": "medium",
    "service_name": "billing-api",
    "target_environment": "stage",
    "operation_type": "deploy",
    "task_type": "deployment_analysis",
    "execution_parameters": {
      "service_name": "billing-api",
      "target_environment": "stage"
    },
    "constraints": []
  },
  "execution_constraints": [
    "Request input is validated and ready for planning."
  ],
  "previous_step_outputs": {},
  "safety_flags": [],
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
  "expected_result": "Deployment analysis defines rollout prerequisites, service impact, and executable recommendations.",
  "result_handoff_condition": "Forward the result when deployment prerequisites, rollout notes, and proposed actions are returned in JSON."
}
```

## Pola obowiązkowe

- `instruction`: precyzyjna instrukcja dla agenta, zawsze niepusta.
- `context`: znormalizowany kontekst operacyjny zgłoszenia.
- `step_id`: identyfikator kroku workflow przekazanego do delegacji.
- `owner_agent`: nazwa agenta odpowiedzialnego za wykonanie kroku.
- `task_type`: jawna klasyfikacja kroku. Dozwolone wartości:
  - `deployment_analysis`
  - `infrastructure_analysis`
  - `ci_cd_analysis`
  - `service_rollout`
  - `environment_change`
  - `pipeline_procedure`
  - `diagnostic_plan`
  - `risk_policy_review`
  - `human_approval`
  - `execution_handoff`
  - `final_report`
- `target_environment`: środowisko docelowe kroku. Dozwolone wartości: `dev`, `stage`, `prod`.
- `technical_params`: techniczne parametry kroku przekazane do agenta.
- `execution_constraints`: lista warunków i ograniczeń wykonania.
- `previous_step_outputs`: dane wejściowe pochodzące z wyników kroków zależnych.
- `safety_flags`: znormalizowane flagi bezpieczeństwa i ryzyka.
- `expected_output_json_format`: deklaracja schematu odpowiedzi oczekiwanej od agenta.
- `expected_result`: opis tego, co agent ma osiągnąć.
- `result_handoff_condition`: warunek, po którym wynik może wrócić do `Supervisor`.

## Zasady walidacji

Walidacja kontraktu jest wykonywana przez model `AgentExecutionInput`.

### 1. Walidacja struktury

- `instruction`, `step_id`, `owner_agent`, `expected_result` i `result_handoff_condition` nie mogą być puste,
- `context` musi zawierać `request_id`, `source`, `user_id`, `user_request`, `priority` i `service_name`,
- `task_type` musi należeć do zdefiniowanego zbioru typów kroków,
- `target_environment` musi należeć do `dev|stage|prod`,
- `technical_params` i `expected_output_json_format` muszą być obiektami JSON.

### 2. Walidacja kompletności

- `technical_params` nie może być puste,
- `expected_output_json_format` nie może być puste,
- `execution_constraints`, `safety_flags` i inne listy tekstowe są normalizowane i deduplikowane,
- każdy agent dostaje pełne `previous_step_outputs`, nawet jeśli jest to pusty obiekt dla kroku bez zależności.

### 3. Walidacja spójności semantycznej

- `technical_params.service_name` musi odpowiadać `context.service_name`,
- `technical_params.target_environment` musi odpowiadać `target_environment`,
- `technical_params.task_type` musi odpowiadać `task_type`,
- `operation_type` jest dokładany do `technical_params`, jeżeli wynika ze znormalizowanego zgłoszenia.

Jeżeli którykolwiek z tych warunków nie jest spełniony, payload nie powinien zostać przekazany do agenta.

## Powiązanie z workflow

Kontrakt jest budowany bezpośrednio z kroku `WorkflowPlanStep` oraz `TaskRequest`. Oznacza to, że:

- `Supervisor` planuje krok z jawnym `task_type`,
- delegacja mapuje krok do `AgentExecutionInput`,
- agent otrzymuje spójny payload niezależnie od domeny,
- `Risk/Policy Agent` i `Execution Agent` używają tego samego kontraktu, ale z innym `task_type` i innym `expected_output_json_format`.

Takie podejście wzmacnia separację odpowiedzialności i pokazuje dojrzałe użycie LangChain Deep Agents: plan jest deklaratywny, wejście do agenta jest wersjonowalne i walidowane, a logika bezpieczeństwa pozostaje po stronie orkiestracji.
