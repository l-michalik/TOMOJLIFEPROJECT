# Specyfikacja projektu: Agentic Platform Engineer z komponentem Supervisor

## 1. Cel dokumentu

Celem projektu jest zbudowanie wieloagentowego systemu klasy Platform Engineer, który automatyzuje zadania DevOps w sposób audytowalny, kontrolowany i zgodny z politykami bezpieczeństwa. System przyjmuje zgłoszenia z Jira, czatu lub API, planuje ich realizację, deleguje wykonanie do wyspecjalizowanych agentów oraz zapewnia obowiązkowe bramki autoryzacji dla operacji podwyższonego ryzyka.

Niniejszy dokument utrwala architekturę docelową systemu oraz precyzuje rolę komponentu `Supervisor` jako głównego koordynatora workflow.

## 2. Zakres projektu

System obejmuje:

- przyjmowanie zadań operacyjnych z kanałów Jira, chat oraz API,
- walidację danych wejściowych i standaryzację żądań,
- planowanie wieloetapowego workflow,
- delegowanie podzadań do wyspecjalizowanych agentów,
- ocenę ryzyka i zgodności planowanych działań,
- wykonanie zatwierdzonych operacji przez komponent wykonawczy,
- agregację wyników, logów i artefaktów,
- generowanie raportu końcowego dla użytkownika,
- pełny tracing, checkpointing i audyt działań.

Poza zakresem `Supervisor` pozostaje bezpośrednie wykonywanie operacji infrastrukturalnych, uruchamianie komend administracyjnych oraz obchodzenie mechanizmów autoryzacji.

## 3. Cele biznesowe i techniczne

### 3.1 Cele biznesowe

- skrócenie czasu realizacji zadań DevOps z dni lub tygodni do godzin,
- ograniczenie błędów manualnych przy wdrożeniach i zmianach infrastrukturalnych,
- zwiększenie transparentności procesów operacyjnych,
- zapewnienie spójnego procesu autoryzacji działań krytycznych.

### 3.2 Cele techniczne

- zbudowanie stabilnego wieloagentowego systemu orkiestracji,
- zapewnienie pełnego śladu audytowego każdego kroku workflow,
- odseparowanie planowania od wykonywania zmian,
- wymuszenie polityk bezpieczeństwa i kontroli uprawnień.

### 3.3 Metryki sukcesu

- średni czas realizacji zadania: cel `< 1h`,
- czas do pierwszej odpowiedzi systemu: cel `< 5 min`,
- skuteczność wdrożeń: cel `> 99%` dla scenariuszy objętych automatyzacją,
- dostępność usługi: cel `>= 99,5%`,
- udział zadań zakończonych z kompletnym raportem i trace: cel `100%`,
- liczba działań wykonanych bez wymaganej autoryzacji: cel `0`.

## 4. Interesariusze i role

- `Administrator Systemu` odpowiada za konfigurację platformy, zarządzanie uprawnieniami, środowiskami i politykami.
- `Inżynier DevOps / Platform Engineer` zgłasza zadania, dostarcza parametry, akceptuje lub odrzuca działania wymagające autoryzacji oraz odbiera raport końcowy.
- `Supervisor` koordynuje przebieg workflow od przyjęcia zgłoszenia do zamknięcia zadania.
- `DeploymentAgent` przygotowuje i prowadzi czynności związane z deploymentem aplikacji i usług.
- `InfraAgent` przygotowuje i prowadzi czynności związane z infrastrukturą, konfiguracją środowisk i zasobów.
- `CI_CD_Agent` przygotowuje i prowadzi czynności dotyczące pipeline'ów, walidacji buildów, testów i release flow.
- `Risk/Policy Agent` analizuje planowane działania pod kątem zgodności, ryzyka i konieczności uzyskania zgód.
- `Execution Agent / Toolrunner` wykonuje wyłącznie zatwierdzone operacje techniczne przez kontrolowane narzędzia i integracje.

## 5. Przypadki użycia

- użytkownik zgłasza przez Jira, chat lub API prośbę o wdrożenie, zmianę konfiguracji albo diagnostykę,
- system doprecyzowuje brakujące parametry i waliduje kompletność wejścia,
- Supervisor tworzy plan i rozdziela pracę między agentów specjalistycznych,
- wyniki cząstkowe są agregowane i oceniane przez Risk/Policy Agent,
- działania wymagające zgody są wstrzymywane do czasu decyzji użytkownika,
- Execution Agent wykonuje tylko te akcje, które zostały dopuszczone polityką i autoryzacją,
- użytkownik otrzymuje raport końcowy ze statusem, logami i listą wykonanych oraz zablokowanych działań.

## 6. Wymagania funkcjonalne

### 6.1 Kanały wejściowe

System musi obsługiwać co najmniej:

- zgłoszenia z Jira przez webhook lub integrację API,
- komunikację przez interfejs czatowy,
- bezpośrednie wywołania API typu `POST /api/tasks`.

### 6.2 Obsługa zadań

System musi:

- przyjąć i znormalizować żądanie do wspólnego modelu danych,
- wykryć typ zadania, środowisko docelowe, priorytet i ograniczenia,
- zwalidować wymagane pola wejściowe,
- wygenerować plan kroków i przypisać właściciela każdego kroku,
- uruchomić podzadania synchronicznie lub asynchronicznie,
- agregować wyniki i stany pośrednie,
- kierować planowane akcje do oceny ryzyka,
- wstrzymać workflow, jeżeli polityka wymaga autoryzacji,
- wznowić workflow po decyzji użytkownika,
- wygenerować raport końcowy i opublikować go do kanału źródłowego.

### 6.3 Audyt i obserwowalność

System musi rejestrować:

- źródło zgłoszenia i identyfikator użytkownika,
- wejście po walidacji i normalizacji,
- plan workflow i kolejne zmiany stanu,
- decyzje Risk/Policy Agent,
- wymagane i uzyskane zgody,
- działania wykonawcze wraz z ich rezultatami,
- końcowy status zadania oraz artefakty.

## 7. Wymagania niefunkcjonalne

### 7.1 Bezpieczeństwo

- wszystkie operacje narzędziowe muszą podlegać allowliście,
- dane wrażliwe muszą być maskowane w logach i raportach,
- sekrety muszą być przechowywane w dedykowanym menedżerze sekretów,
- operacje krytyczne muszą przechodzić przez Risk/Policy Agent i mechanizm autoryzacji,
- żaden komponent planujący nie może wykonywać zmian bezpośrednio.

### 7.2 Wydajność i skalowalność

- system powinien obsługiwać co najmniej 100 równoległych zadań,
- komponenty muszą skalować się horyzontalnie,
- stan workflow musi być trwały i możliwy do wznowienia po awarii.

### 7.3 Dostępność i zgodność

- usługa powinna działać 24/7,
- system musi wspierać retencję i nieusuwalność logów audytowych,
- projekt powinien być zgodny z wymaganiami RODO/GDPR, jeśli przetwarzane są dane osobowe.

## 8. Architektura logiczna

### 8.1 Główne komponenty

- `Supervisor`
- `DeploymentAgent`
- `InfraAgent`
- `CI_CD_Agent`
- `Risk/Policy Agent`
- `Execution Agent`
- `Human Review Interface`
- `Logging/Tracing`
- `Checkpointer DB`
- `Message Queue`
- integracje z Jira, chatem, repozytoriami, chmurą i narzędziami DevOps

### 8.2 Główny przepływ danych

1. Użytkownik wysyła request z Jira, chatu lub API.
2. Supervisor odbiera request i normalizuje go do wspólnego kontraktu wejściowego.
3. Supervisor wykonuje walidację wejścia.
4. Supervisor tworzy plan workflow i deleguje podzadania do `DeploymentAgent`, `InfraAgent` i `CI_CD_Agent`.
5. Agenci specjalistyczni analizują przydzielone kroki i zwracają wyniki, rekomendacje, logi oraz proponowane akcje.
6. Supervisor agreguje wyniki i buduje listę planowanych akcji wykonawczych.
7. Supervisor przekazuje planowane akcje do `Risk/Policy Agent`.
8. `Risk/Policy Agent` klasyfikuje akcje jako dozwolone, zabronione lub wymagające autoryzacji.
9. Jeśli wymagana jest zgoda, workflow przechodzi do `Human Review Interface` i czeka na decyzję.
10. Dopiero po pozytywnej decyzji `Execution Agent` wykonuje zatwierdzone działania.
11. Wyniki wykonania wracają do Supervisora.
12. Supervisor generuje raport końcowy i publikuje go do źródłowego kanału komunikacji.

## 9. Specyfikacja komponentu Supervisor

### 9.1 Rola

`Supervisor` jest głównym koordynatorem workflow. Odpowiada za przyjęcie zgłoszenia, walidację danych, planowanie kroków, delegowanie pracy, agregację wyników, przekazanie planowanych działań do oceny ryzyka oraz wygenerowanie raportu końcowego.

### 9.2 Odpowiedzialności Supervisora

Supervisor:

- odbiera request z Jira, chatu lub API,
- mapuje wejście do wspólnego kontraktu zadania,
- wykonuje walidację formalną i semantyczną danych wejściowych,
- identyfikuje brakujące informacje i inicjuje proces doprecyzowania,
- planuje kroki workflow,
- deleguje podzadania do `DeploymentAgent`, `InfraAgent` oraz `CI_CD_Agent`,
- śledzi status realizacji podzadań,
- zbiera i agreguje wyniki cząstkowe,
- konsoliduje planowane akcje do wykonania,
- przekazuje planowane akcje do oceny przez `Risk/Policy Agent`,
- podejmuje decyzję o kontynuacji workflow wyłącznie na podstawie wyniku polityki i autoryzacji,
- generuje raport końcowy dla użytkownika i systemów zewnętrznych.

### 9.3 Jawne ograniczenia odpowiedzialności

Supervisor nie może:

- wykonywać bezpośrednio operacji infrastrukturalnych,
- uruchamiać komend administracyjnych na środowiskach,
- wywoływać narzędzi wykonawczych z pominięciem `Execution Agent`,
- samodzielnie zatwierdzać działań wymagających autoryzacji użytkownika,
- omijać `Risk/Policy Agent`,
- obchodzić bramek bezpieczeństwa, allowlist, sandboxingu ani kontroli dostępu.

To ograniczenie jest wymaganiem architektonicznym i bezpieczeństwa, a nie wyłącznie dobrą praktyką implementacyjną.

### 9.4 Wejścia Supervisora

Supervisor przyjmuje zunifikowany model wejściowy:

```json
{
  "request_id": "string",
  "source": "jira|chat|api",
  "user_id": "string",
  "task_description": "string",
  "parameters": {},
  "context": {
    "environment": "dev|stage|prod",
    "priority": "low|medium|high",
    "ticket_id": "string",
    "conversation_id": "string"
  }
}
```

### 9.5 Wyjścia Supervisora

Po etapie planowania:

```json
{
  "request_id": "string",
  "status": "planned",
  "plan": [
    {
      "step_id": "string",
      "owner_agent": "DeploymentAgent|InfraAgent|CI_CD_Agent",
      "goal": "string",
      "inputs": {},
      "depends_on": []
    }
  ]
}
```

Po zakończeniu workflow:

```json
{
  "request_id": "string",
  "status": "completed|failed|blocked",
  "summary": "string",
  "executed_actions": [],
  "blocked_actions": [],
  "approvals": [],
  "artifacts": [],
  "logs_reference": []
}
```

### 9.6 Etapy pracy Supervisora

#### Etap 1. Odbiór requestu

Supervisor odbiera zgłoszenie z kanału wejściowego, zapisuje metadane i nadaje identyfikator workflow.

#### Etap 2. Walidacja wejścia

Supervisor sprawdza:

- kompletność pól obowiązkowych,
- poprawność typu zadania,
- poprawność wskazania środowiska,
- zgodność parametrów z oczekiwanym schematem,
- możliwość bezpiecznego przetworzenia instrukcji.

W przypadku braków Supervisor nie uruchamia dalszych kroków wykonawczych, lecz żąda uzupełnienia danych.

#### Etap 3. Planowanie

Supervisor rozbija zadanie na kroki, określa zależności, priorytety i przypisuje kroki do agentów specjalistycznych.

#### Etap 4. Delegowanie

Supervisor przekazuje podzadania do:

- `DeploymentAgent` dla zadań związanych z wdrożeniem aplikacji,
- `InfraAgent` dla zadań infrastrukturalnych i środowiskowych,
- `CI_CD_Agent` dla zadań pipeline, build, test i release.

#### Etap 5. Agregacja wyników

Supervisor odbiera wyniki, statusy, logi i rekomendacje od agentów specjalistycznych. Na tym etapie nie wykonuje jeszcze zmian, a jedynie konsoliduje obraz sytuacji i proponowanych działań.

#### Etap 6. Przekazanie do Risk/Policy Agent

Supervisor przekazuje listę planowanych akcji do oceny. Jest to obowiązkowa bramka decyzyjna dla działań wykonawczych.

#### Etap 7. Obsługa autoryzacji

Jeżeli `Risk/Policy Agent` oznaczy akcję jako wymagającą zgody:

- Supervisor zatrzymuje workflow,
- publikuje prośbę o akceptację do odpowiedniego kanału,
- zapisuje checkpoint,
- wznawia proces dopiero po otrzymaniu jednoznacznej decyzji.

#### Etap 8. Finalizacja i raport

Po zakończeniu wykonania przez `Execution Agent`, Supervisor zbiera wyniki końcowe i generuje raport zawierający status, listę działań, logi, decyzje autoryzacyjne oraz rekomendacje dalszych kroków.

### 9.7 Reguły decyzyjne Supervisora

- jeżeli wejście jest niekompletne, workflow przechodzi do stanu `waiting_for_input`,
- jeżeli agent specjalistyczny zwróci błąd, Supervisor może zaplanować retry albo zakończyć zadanie statusem `failed`,
- jeżeli polityka zabrania działania, Supervisor oznacza krok jako `blocked` i nie przekazuje go do wykonania,
- jeżeli wymagana jest akceptacja człowieka, Supervisor nie może kontynuować samodzielnie,
- jeżeli wykonanie zakończy się częściowo, Supervisor musi oznaczyć wynik jako częściowy i ująć to w raporcie.

## 10. Specyfikacja agentów specjalistycznych

### 10.1 DeploymentAgent

`DeploymentAgent` odpowiada wyłącznie za analizę i przygotowanie zadań wdrożeniowych dotyczących aplikacji i usług.

Zakres odpowiedzialności:

- rollout aplikacji i usług,
- release sequencing i kolejność wdrożeń zależnych komponentów,
- strategia wdrożenia typu rolling, blue/green lub canary, jeżeli wynika to z kontekstu zadania,
- plan rollbacku i warunki bezpiecznego wycofania wersji,
- wymagania dotyczące dostępności usługi podczas wdrożenia,
- walidacja gotowości artefaktu do wdrożenia z perspektywy deploymentu.

Typy obsługiwanych zadań:

- deploy nowej wersji usługi,
- restart lub redeploy komponentu aplikacyjnego,
- rollout hotfixa,
- promotion release między środowiskami,
- przygotowanie kolejności wdrożenia dla wielu usług.

Granice decyzyjne:

- może proponować kroki deploymentu, zależności i warunki wstępne,
- może wskazać potrzebę rollbacku, smoke testów lub okna wdrożeniowego,
- nie wykonuje zmian samodzielnie,
- nie podejmuje decyzji politycznych ani autoryzacyjnych,
- nie zmienia konfiguracji infrastruktury, chyba że jedynie wskazuje zależność do przekazania `InfraAgent`,
- nie uruchamia pipeline ani narzędzi wykonawczych z pominięciem `Execution Agent`.

Relacje:

- przyjmuje podzadanie wyłącznie od `Supervisor`,
- zwraca analizę, rekomendacje, logi i proponowane akcje wyłącznie do `Supervisor`,
- jego propozycje są oceniane przez `Risk/Policy Agent`,
- wykonanie zaproponowanych akcji może nastąpić wyłącznie przez `Execution Agent`.

### 10.2 InfraAgent

`InfraAgent` odpowiada wyłącznie za analizę i przygotowanie zmian infrastrukturalnych, środowiskowych oraz konfiguracyjnych.

Zakres odpowiedzialności:

- zasoby chmurowe i platformowe,
- konfiguracja środowisk,
- zależności sieciowe, storage, compute i IAM wynikające ze zgłoszenia,
- sekrety, zmienne środowiskowe i konfiguracja platformowa na poziomie planowania,
- wpływ zmian na współdzielone komponenty infrastrukturalne,
- identyfikacja prerekwizytów dla deploymentu i pipeline.

Typy obsługiwanych zadań:

- utworzenie lub modyfikacja zasobów infrastrukturalnych,
- zmiana konfiguracji środowiska,
- aktualizacja secretów lub parametrów runtime,
- analiza zależności sieciowych, uprawnień i storage,
- przygotowanie zmian wymaganych przed wdrożeniem aplikacji.

Granice decyzyjne:

- może identyfikować wpływ techniczny, zależności i ryzyka infrastrukturalne,
- może proponować akcje typu `infra_change`, `config_update`, `secret_rotation` lub `permission_change`,
- nie zatwierdza ryzyka i nie klasyfikuje zgodności z polityką,
- nie wykonuje komend administracyjnych ani zmian środowiskowych,
- nie przejmuje zadań rolloutowych należących do `DeploymentAgent`,
- nie zmienia pipeline'ów należących do `CI_CD_Agent`.

Relacje:

- dostaje zakres prac od `Supervisor`,
- przekazuje wynik analizy tylko do `Supervisor`,
- jego propozycje trafiają do `Risk/Policy Agent` przed jakimkolwiek wykonaniem,
- zatwierdzone akcje są realizowane wyłącznie przez `Execution Agent`.

### 10.3 CI_CD_Agent

`CI_CD_Agent` odpowiada wyłącznie za analizę i przygotowanie zadań dotyczących pipeline'ów, buildów, testów, artefaktów i release flow.

Zakres odpowiedzialności:

- workflow build i test,
- gating jakościowy przed wdrożeniem,
- artefakty release i ich gotowość,
- konfiguracja pipeline oraz release automation,
- zależności między walidacją jakości a deploymentem,
- rekomendacje dotyczące kolejności build, test, publish i release.

Typy obsługiwanych zadań:

- zmiana pipeline CI lub CD,
- wymaganie dodatkowych testów lub walidacji quality gates,
- analiza przepływu artefaktów,
- przygotowanie release flow,
- diagnostyka problemów w buildach, testach i automatyzacji dostarczania.

Granice decyzyjne:

- może rekomendować akcje dotyczące pipeline, testów, release i artefaktów,
- może wskazywać brakujące walidacje lub wymagane quality gates,
- nie wykonuje pipeline'ów i nie uruchamia buildów samodzielnie,
- nie zatwierdza wyjątków od polityk,
- nie przejmuje odpowiedzialności za zmiany infrastrukturalne ani rollout aplikacji,
- nie omija `Risk/Policy Agent` ani `Execution Agent`.

Relacje:

- pracuje wyłącznie na podstawie delegacji od `Supervisor`,
- zwraca wynik tylko do `Supervisor`,
- planowane akcje są przekazywane przez `Supervisor` do `Risk/Policy Agent`,
- działania dopuszczone do wykonania realizuje tylko `Execution Agent`.

### 10.4 Wspólne reguły dla agentów specjalistycznych

Każdy agent specjalistyczny:

- realizuje wyłącznie swoją klasę zadań,
- nie podejmuje samodzielnej orkiestracji całego workflow,
- nie wywołuje narzędzi wykonawczych bezpośrednio,
- nie omija polityk bezpieczeństwa, approval gate ani sandboxingu,
- zwraca wynik, logi, rekomendacje i proponowane akcje do `Supervisor`,
- może wskazać zależność na innego agenta, ale nie deleguje pracy poza kontrolą `Supervisor`.

## 11. Specyfikacja Risk/Policy Agent

`Risk/Policy Agent` odpowiada za ocenę zgodności i ryzyka. Dla każdej planowanej akcji musi określić:

- czy akcja jest dozwolona,
- czy akcja jest zabroniona,
- czy akcja wymaga dodatkowej autoryzacji,
- jakie jest uzasadnienie decyzji,
- które polityki lub reguły zostały zastosowane.

Przykładowy kontrakt:

```json
{
  "actions": [
    {
      "action_id": "string",
      "type": "deploy|infra_change|pipeline_change|restart|delete",
      "environment": "dev|stage|prod",
      "details": {}
    }
  ]
}
```

Wynik:

```json
{
  "decisions": [
    {
      "action_id": "string",
      "allowed": true,
      "requires_approval": false,
      "reason": "string"
    }
  ]
}
```

## 12. Specyfikacja Execution Agent

`Execution Agent` jest jedynym komponentem uprawnionym do wykonywania zatwierdzonych operacji technicznych. Działa przez kontrolowane narzędzia, integracje i sandbox.

Wymagania:

- wykonuje tylko akcje zatwierdzone przez `Risk/Policy Agent`,
- respektuje decyzje `Human Review Interface`,
- korzysta wyłącznie z dozwolonych narzędzi i endpointów,
- zapisuje pełne logi wykonania,
- zwraca status i artefakty do Supervisora.

## 13. Kontrakty integracyjne

### 13.1 API wejściowe

`POST /api/tasks`

```json
{
  "taskDescription": "Deploy service X to stage",
  "parameters": {
    "service": "service-x",
    "environment": "stage"
  }
}
```

### 13.2 Wynik planowania

```json
{
  "request_id": "REQ-123",
  "status": "planned",
  "plan": [
    {
      "step_id": "STEP-1",
      "owner_agent": "DeploymentAgent",
      "goal": "Prepare deployment of service-x to stage"
    }
  ],
  "confidence": 0.95
}
```

### 13.3 Wynik wykonania

```json
{
  "request_id": "REQ-123",
  "status": "completed",
  "results": [
    {
      "agent": "DeploymentAgent",
      "status": "success",
      "details": "Deployment completed"
    }
  ]
}
```

## 14. Zasady bezpieczeństwa i autoryzacji

### 14.1 Twarde reguły architektoniczne

- `Supervisor` nie wykonuje bezpośrednio operacji infrastrukturalnych.
- `Supervisor` nie omija bramek autoryzacji.
- żadna akcja wykonywalna nie trafia do realizacji bez oceny `Risk/Policy Agent`,
- akcje wysokiego ryzyka wymagają `Human-in-the-Loop`,
- wszystkie wywołania narzędzi muszą przechodzić walidację schematu i allowlistę.

### 14.2 Przykłady akcji wymagających autoryzacji

- restart usług produkcyjnych,
- usuwanie zasobów,
- zmiany w środowisku `prod`,
- modyfikacja sieci, polityk dostępu i sekretów,
- uruchomienie `terraform apply`, `kubectl delete`, zmian rollback/rollforward o wysokim wpływie.

## 15. Dane, persystencja i obserwowalność

- `Checkpointer DB` przechowuje stan workflow i punkty wznowienia,
- `Message Queue` obsługuje komunikację asynchroniczną między komponentami,
- logi i trace są zapisywane w systemie obserwowalności,
- artefakty są przechowywane w magazynie obiektowym lub współdzielonym storage,
- logi muszą być możliwe do powiązania z `request_id`, `user_id` i `approval_id`.

## 16. Proponowany stos technologiczny

- orkiestracja agentów: `Deep Agents / LangGraph`,
- warstwa API: `FastAPI`,
- checkpointer: `PostgreSQL` lub `SQLite` dla środowisk nieprodukcyjnych,
- kolejka: `Kafka` lub `RabbitMQ`,
- storage artefaktów: `S3` lub odpowiednik,
- sekrety: `HashiCorp Vault` lub `AWS Secrets Manager`,
- tracing i ewaluacja: `LangSmith` lub `OpenTelemetry`,
- CI/CD: `GitHub Actions` lub `Jenkins`.

## 17. Plan wdrożenia

### 17.1 Środowiska

- `DEV` dla lokalnego rozwoju,
- `STAGE` jako środowisko zbliżone do produkcyjnego,
- `PROD` dla ruchu produkcyjnego.

### 17.2 Strategia wdrożeń

- infrastruktura jako kod,
- konteneryzacja komponentów,
- wdrożenia na Kubernetes lub równoważnej platformie,
- strategia `Blue-Green` albo `Rolling Update` zależnie od komponentu,
- przygotowany plan rollbacku.

## 18. Roadmapa

### Etap 0. Przygotowanie

- analiza wymagań,
- model danych,
- środowisko developerskie,
- wybór technologii.

### Etap 1. MVP

- Supervisor,
- jeden agent specjalistyczny,
- integracja Jira,
- read-only execution,
- podstawowy approval workflow.

### Etap 2. Wersja v1

- pełny zestaw agentów specjalistycznych,
- integracje z narzędziami wykonawczymi,
- polityki bezpieczeństwa,
- pełne logowanie i alerty.

### Etap 3. Wersja v2

- rozszerzone integracje,
- autoskalowanie,
- testy chaos,
- optymalizacje wydajnościowe i kosztowe.

## 19. Artefakty końcowe projektu

- kod źródłowy komponentów i integracji,
- dokumentacja techniczna i wdrożeniowa,
- definicje polityk bezpieczeństwa,
- zestawy testów i dane testowe,
- dashboardy obserwowalności,
- scenariusz demo z pełnym przebiegiem workflow.

## 20. Podsumowanie architektoniczne

Projekt zakłada ścisłe rozdzielenie odpowiedzialności między planowaniem, oceną ryzyka i wykonaniem. `Supervisor` pełni rolę nadrzędnego koordynatora procesu, ale nie jest komponentem wykonawczym. Każda planowana akcja przechodzi przez ocenę `Risk/Policy Agent`, a działania wysokiego ryzyka wymagają jawnej autoryzacji użytkownika. Taki model zapewnia audytowalność, bezpieczeństwo, możliwość wznowienia procesów oraz kontrolowaną automatyzację operacji DevOps.
