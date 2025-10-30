# Rozproszone łamanie hashy

Projekt składa się z ogólnej biblioteki do permutacji oraz aplikacji rozproszonej do łamania hashy w sieci lokalnej (Wi-Fi). System dzieli zadania na paczki i komunikuje się z węzłami przez UDP. Sam proces łamania hashy może być realizowany przez zewnętrzną bibliotekę (np. `hashlib`, `passlib`).

# Skrótowy opis

Biblioteka ogólna do permutacji, a w apce do łamania hasha
Logi do weryfikacji czy to poprawnie działa.  Odpalamy na dowolnym bez IP. Sieć lokalna wifi.
Paczki - odkrywamy że jest mode. Od paczki, patrzę która rozwiązałem (wzięte), zrobione, robione, do zrobienia typy paczkę. Komunikacja po UDP. Jeżeli jeden node skończy to daje info co tam jest.

# INFO
Do smaego liczenia hasha mozna uzyc zewnterznej biblioetki - 
aplikacja do tego moze wygaac bezydko nawet w shell

# Rozproszone łamanie hashy

Projekt składa się z ogólnej biblioteki do permutacji oraz aplikacji rozproszonej do łamania hashy w sieci lokalnej (Wi‑Fi).

* System dzieli zadania na paczki i komunikuje się z węzłami przez UDP.
* Sam proces łamania hashy może być realizowany przez zewnętrzną bibliotekę (np. `hashlib`, `passlib`).

## Biblioteka i aplikacja

* Biblioteka ogólna do permutacji, a w apce do łamania hasha.
* Logi do weryfikacji czy to poprawnie działa.
* Odpalamy na dowolnym bez IP. Sieć lokalna wifi.

## Paczki i stan zadań

* Paczki — odkrywamy że jest node. Pierwszy komputer to pierwszy node - bierze jedna paczke
* Od paczki patrzę która rozwiązałem:  `zrobione`, `robione`, `do zrobienia` — typy paczkę.
* Jeżeli jeden node skończy to daje info co tam jest (z hashem czy bez jak bez to liczymy dalej a jak z to konczymy)
* Zapamiętywanie, w której paczce nie ma hasha.

## Komunikacja

* Komunikacja po UDP.

## Hashe i liczenie

* Do samego liczenia hasha można użyć zewnętrznej biblioteki.
* Aplikacja do tego może wyglądać bezpłciowo, nawet w shell.

## Architekturalna uwaga

* by the way - skoro mają być paczki to który komputer ma o nich pamiętać?? **NIE MOŻE BYĆ SERWERA!!**