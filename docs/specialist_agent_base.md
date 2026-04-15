# Wspólna baza techniczna agentów specjalistycznych

Dokument opisuje wspólną warstwę wykonawczą dla agentów `DeploymentAgent`, `InfraAgent`, `CI_CD_Agent`, `Risk/Policy Agent`, `Execution Agent` oraz kolejnych agentów specjalistycznych.

## Cel

`BaseSpecialistAgent` eliminuje duplikację wspólnej logiki wykonawczej. Każdy agent specjalistyczny korzysta z tej samej ścieżki:

- przyjmuje wejście zgodne z `AgentExecutionInput`,
- waliduje kontrakt wejściowy,
- buduje kontekst roboczy i prompt,
- uruchamia `deepagents.create_deep_agent`,
- przekazuje narzędzia do agenta,
- zapisuje log żądania i odpowiedzi,
- normalizuje wynik do `AgentExecutionOutput`,
- zwraca ustandaryzowany błąd przy problemach z wykonaniem lub kontraktem.

## Zakres odpowiedzialności

Warstwa bazowa obsługuje:

- kontrakt wejścia i wyjścia,
- wspólny format promptu dla workflow,
- statusy kroku zgodne z dokumentem `agent_output_format.md`,
- wywołanie modelu i narzędzi,
- obsługę błędów `invalid_agent_input`, `agent_execution_failed`, `invalid_json_response` i `invalid_agent_output`.

Warstwa bazowa nie zawiera logiki domenowej konkretnego agenta. Domena jest dodawana przez nadpisanie hooków.

## Sposób rozszerzania

Aby utworzyć kolejnego agenta specjalistycznego:

1. Utwórz klasę dziedziczącą po `BaseSpecialistAgent`.
2. Przekaż `model`, `owner_agent`, `system_prompt` i `agent_name`.
3. Nadpisz `build_additional_prompt_sections`, jeśli agent wymaga dodatkowych instrukcji domenowych.
4. Nadpisz `get_tools`, jeśli agent ma korzystać z dedykowanych narzędzi.
5. Wywołuj `run(...)` z payloadem `AgentExecutionInput` albo słownikiem zgodnym z tym kontraktem.

## Integracja z workflow

`utils/workflow_delegation.py` buduje `AgentExecutionInput` dla kroku workflow i uruchamia `BaseSpecialistAgent`. Dzięki temu:

- `Supervisor` i delegacja kroków pozostają cienką warstwą orkiestracji,
- specjalistyczne wykonanie ma jeden spójny punkt wejścia,
- dodawanie kolejnych agentów nie wymaga kopiowania walidacji, promptu, parsowania odpowiedzi ani obsługi błędów.
