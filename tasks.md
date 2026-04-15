Na podstawie specyfikacji projektu zawartej w folderze docs/project_specification.MD, wykonaj zadanie : <Zbudować mechanizm pozwalający Supervisorowi i warstwie orkiestracji przypisać dany krok planu do właściwego agenta wykonawczego. Należy zdefiniować reguły klasyfikacji zadań deploymentowych, infrastrukturalnych i CI/CD, sposób obsługi zadań mieszanych oraz zachowanie w przypadku niejednoznacznego przypisania. Wynikiem ma być jednoznaczny routing kroku do odpowiedniego komponentu.>

Projekt ma być moją wizytówką, ze znam biblioteke langchain deepagents i opanowalem ją na poziomie senior developera.

Zasady developmentu
- Każdy plik z kodem nie może przekraczać 500 linii, z wyjątkiem plików Markdown. Rozwiązanie należy implementować w możliwie najprostszy sposób, minimalizując złożoność oraz unikając nadmiernej abstrakcji i przedwczesnej optymalizacji.
- Nazewnictwo funkcji, typów, zmiennych oraz plików musi być jednoznaczne i opisowe, tak aby jasno komunikowało ich przeznaczenie. Implementacja powinna obejmować wyłącznie wymagania wynikające ze specyfikacji, bez dodawania logiki defensywnej ani spekulatywnej wykraczającej poza określony zakres.
- Struktura projektu powinna zachowywać separację odpowiedzialności, a w razie potrzeby należy wydzielać funkcje, typy i narzędzia do osobnych plików lub katalogów oraz tworzyć nowe elementy struktury, jeśli poprawia to czytelność i skalowalność rozwiązania.
- Refaktoryzacja powinna ograniczać się do fragmentów kodu bezpośrednio związanych z realizowanym zadaniem. Szersze zmiany są dopuszczalne wyłącznie wtedy, gdy są konieczne dla zapewnienia poprawności działania lub spójności architektonicznej.
- Pomiń wszelkie zadania wymagające utworzenia testów