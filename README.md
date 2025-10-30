# Rozproszone łamanie hashy

Projekt składa się z ogólnej biblioteki do permutacji oraz aplikacji rozproszonej do łamania hashy w sieci lokalnej (Wi-Fi). System dzieli zadania na paczki i komunikuje się węzłami przez UDP. Sam proces łamania hashy może być realizowany przez zewnętrzną bibliotekę.

---

## Spis treści
1. [Opis projektu](#opis-projektu)  
2. [Komponenty](#komponenty)  
3. [Wymagania](#wymagania)  
4. [Uruchomienie](#uruchomienie)  
5. [Architektura sieciowa](#architektura-sieciowa)  
6. [Paczki i stany](#paczki-i-stany)  
7. [Protokół komunikacji UDP](#protokol-komunikacji-udp)  
8. [Logi i weryfikacja](#logi-i-weryfikacja)  
9. [Uwagi](#uwagi)

---

## Opis projektu
Celem projektu jest stworzenie systemu rozproszonego do łamania hashy w sieci lokalnej, który:
- dzieli przestrzeń permutacji na paczki,  
- przydziela je węzłom w sieci lokalnej,  
- śledzi postęp i statusy paczek,  
- komunikuje się przez UDP bez potrzeby hardkodowania IP,  
- loguje przebieg do późniejszej weryfikacji.

---

## Komponenty
- **perm-lib** — biblioteka generująca/permutująca kombinacje i zakresy permutacji.  
- **cracker-app** — aplikacja rozproszona, odbiera paczki, testuje hashe (przez zewnętrzną bibliotekę), wysyła statusy.  
- **logs/** — katalog z logami do audytu i weryfikacji pracy węzłów.

---

## Wymagania
- System: Linux / macOS / Windows  
- Język: np. Python 3.10+ (lub dopasowany do implementacji)  
- Sieć lokalna Wi-Fi (węzły w tej samej podsieci, brak konieczności stałego IP)  

---

## Uruchomienie
Przykład uruchomienia węzła:
```bash
python cracker_app.py --mode worker --listen-port 9001 --broadcast-port 9009
