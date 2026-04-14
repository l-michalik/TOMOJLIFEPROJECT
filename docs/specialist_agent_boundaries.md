# Docelowy podział agentów wykonawczych

Ten dokument doprecyzowuje architekturę agentów specjalistycznych opisaną w [project_specification.MD](./project_specification.MD). Celem jest czytelny, wdrażalny podział odpowiedzialności zgodny z modelem orchestration-first: `Supervisor` planuje i agreguje, agenci specjalistyczni analizują swoją klasę zadań, `Risk/Policy Agent` ocenia zgodność, a `Execution Agent` wykonuje wyłącznie wcześniej zatwierdzone działania.

## Zasada nadrzędna

Każdy agent specjalistyczny działa jako wyspecjalizowany planner/analyzer dla jednej domeny operacyjnej. Nie wykonuje zmian samodzielnie, nie obchodzi kontroli bezpieczeństwa i nie komunikuje się bezpośrednio z narzędziami wykonawczymi poza kontraktem zwracanym do `Supervisor`.

## Relacja komponentów

Przepływ odpowiedzialności:

1. `Supervisor` normalizuje request, planuje kroki i przydziela je do właściwych agentów.
2. `DeploymentAgent`, `InfraAgent` i `CI_CD_Agent` przygotowują wynik domenowy zawierający analizę, rekomendacje i proponowane akcje.
3. `Supervisor` agreguje wyniki i buduje wspólną listę planowanych akcji.
4. `Risk/Policy Agent` ocenia każdą akcję jako `allowed`, `blocked` albo `requires_approval`.
5. `Execution Agent` wykonuje tylko akcje dopuszczone przez politykę i autoryzację.
6. Wynik wykonania wraca do `Supervisor`, który zamyka workflow i generuje raport.

## DeploymentAgent

Misja:
Przygotowanie planu wdrożenia aplikacji lub usługi bez wchodzenia w bezpośrednie wykonanie zmian.

Zakres odpowiedzialności:

- rollout i release sequencing,
- strategia deploymentu,
- rollback plan,
- analiza prerekwizytów wdrożenia,
- wymagania na smoke tests, health checks i service readiness,
- określenie wpływu wdrożenia na dostępność usługi.

Obsługiwane zadania:

- deploy nowej wersji,
- redeploy lub restart usługi,
- promotion release między środowiskami,
- rollout hotfixa,
- planowanie wdrożeń zależnych usług.

Poza zakresem:

- provisioning infrastruktury,
- modyfikacja secretów i IAM,
- zmiany w pipeline CI/CD,
- samodzielne uruchamianie deploymentu.

Granice decyzyjne:

- może proponować sekwencję działań i warunki startowe,
- może wskazać, że potrzebna jest analiza `InfraAgent` lub `CI_CD_Agent`,
- nie może samodzielnie zaakceptować ryzyka produkcyjnego,
- nie może uruchomić wykonania bez `Risk/Policy Agent` i `Execution Agent`.

Kontrakt względem Supervisora:

- wejście: krok workflow przypisany do deploymentu,
- wyjście: podsumowanie, findings, proposed_actions, ryzyka, artefakty,
- kanał zwrotny: wyłącznie `Supervisor`.

## InfraAgent

Misja:
Przygotowanie zmian infrastrukturalnych i środowiskowych potrzebnych do realizacji requestu.

Zakres odpowiedzialności:

- zasoby cloud/platform,
- konfiguracja środowisk,
- zależności sieciowe i storage,
- IAM i permission scope na poziomie planowania,
- sekrety i parametry runtime jako temat analizy,
- identyfikacja wpływu na komponenty współdzielone.

Obsługiwane zadania:

- zmiana konfiguracji środowiska,
- przygotowanie zasobów pod wdrożenie,
- analiza wpływu zmian sieciowych,
- aktualizacja konfiguracji lub secretów,
- zmiany zależności platformowych.

Poza zakresem:

- release sequencing,
- strategia rolloutu aplikacji,
- konfiguracja pipeline,
- bezpośrednie wykonywanie zmian administracyjnych.

Granice decyzyjne:

- może proponować technicznie konieczne akcje infrastrukturalne,
- może klasyfikować ryzyka techniczne i zależności,
- nie może określać, że akcja jest dozwolona politycznie,
- nie może wykonywać akcji ani omijać approval gates.

Kontrakt względem Supervisora:

- wejście: krok workflow dotyczący infrastruktury lub środowiska,
- wyjście: analiza wpływu, proposed_actions, zależności, ryzyka,
- kanał zwrotny: wyłącznie `Supervisor`.

## CI_CD_Agent

Misja:
Przygotowanie zmian dotyczących pipeline'ów, walidacji jakości, buildów i release automation.

Zakres odpowiedzialności:

- pipeline CI/CD,
- build, test i publish flow,
- quality gates,
- gotowość artefaktów,
- release automation,
- diagnoza problemów w automatyzacji dostarczania.

Obsługiwane zadania:

- zmiana pipeline,
- dodanie lub korekta quality gates,
- analiza artefaktów release,
- przygotowanie release flow,
- diagnoza build/test failures.

Poza zakresem:

- deployment runtime,
- provisioning infrastruktury,
- wykonanie buildów lub pipeline'ów bez zatwierdzenia,
- decyzje compliance i approval.

Granice decyzyjne:

- może proponować kroki walidacji i zmiany w automation flow,
- może wskazywać brakujące testy, build stages lub publish stages,
- nie może samodzielnie uruchamiać pipeline execution,
- nie może przenieść akcji do wykonania z pominięciem `Supervisor`.

Kontrakt względem Supervisora:

- wejście: krok workflow dotyczący CI/CD,
- wyjście: analiza pipeline, proposed_actions, quality risks, artifacts,
- kanał zwrotny: wyłącznie `Supervisor`.

## Relacja z Risk/Policy Agent

`Risk/Policy Agent` nie planuje domenowo deploymentu, infrastruktury ani CI/CD. Ocenia tylko skutki proponowanych akcji i decyduje:

- czy akcja jest dozwolona,
- czy akcja jest zablokowana,
- czy akcja wymaga autoryzacji człowieka,
- jakie reguły i uzasadnienie doprowadziły do decyzji.

Agenci specjalistyczni nie mogą obchodzić tej bramki przez:

- oznaczanie własnych akcji jako automatycznie dozwolonych,
- pomijanie akcji wysokiego ryzyka w celu skrócenia workflow,
- delegowanie działań bezpośrednio do `Execution Agent`.

## Relacja z Execution Agent

`Execution Agent` jest jedynym komponentem uprawnionym do wykonania technicznej zmiany. Agenci specjalistyczni:

- nie wykonują komend,
- nie wywołują narzędzi,
- nie modyfikują środowisk,
- nie prowadzą własnych obejść sandboxu ani polityk.

Ich zadaniem jest przygotowanie precyzyjnego wejścia do etapu execution, a nie wykonanie operacji.

## Reguły implementacyjne dla Deep Agents

W implementacji Deep Agents każdy agent specjalistyczny powinien mieć:

- własny system prompt opisujący domenę i zakazane działania,
- jednoznaczny zakres odpowiedzialności bez nakładania się z innymi agentami,
- kontrakt wyjściowy zwracany w JSON,
- jawne pole `proposed_actions`, które dopiero `Supervisor` agreguje i przekazuje dalej,
- instrukcję zwrotu wyniku wyłącznie do `Supervisor`.

Ten model wzmacnia architekturę separacji odpowiedzialności i pokazuje dojrzałe użycie agentów wyspecjalizowanych zamiast pojedynczego, nadmiernie szerokiego agenta wykonawczego.
