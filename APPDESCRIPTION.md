# **Jednostronicowa notatka: Wzorce projektowe w projekcie – analiza, komunikacja, przepływ i uzasadnienie**

---

## **1. Struktura projektu – dwa światy**
- **`library/`** – **czysty silnik permutacji**: niezależny, testowalny, bez sieci, bez wątków.  
- **`app/main.py`** – **aplikacja rozproszona**: używa biblioteki do łamania hasha w sieci P2P.

> **Klucz**: biblioteka **nie wie** o wątkach, UDP, multicast. Aplikacja **nie wie**, jak działa generator – tylko że działa.

---

## **2. Wzorce – gdzie, jak, dlaczego, co się przekazuje**

| Wzorzec | Gdzie | Jak | Dlaczego | Co się przekazuje |
|--------|------|-----|---------|-------------------|
| **Abstract Factory** | `library/factory.py` | `GeneratorFactory.default_bruteforce()` | Szybkie tworzenie gotowych generatorów bez konfigurowacji | `min_len`, `max_len` → zwraca `PasswordGenerator` |
| **Builder** | `library/builder.py` | `GeneratorBuilder().with_default_alphabet().with_length_range(...).build()` | Krokowa konfiguracja – czytelne API | `charset`, `min_len`, `max_len` → buduje `PasswordGenerator` |
| **Strategy** | `library/strategies.py` + `generator.py` | `BruteForceStrategy` deleguje do `CoreBruteGenerator` | Wymienne algorytmy (przyszłość: maski, słowniki) | `alphabet`, `min_length`, `max_length` |
| **Iterator** | `CoreBruteGenerator.BatchIterator` + `PermutationIterator` | Leniwe generowanie haseł po indeksie | Oszczędność pamięci, podział na paczki | `start_idx`, `count` → `str` (hasło) |

---

## **3. Przepływ sterowania – krok po kroku**

### **Krok 1: Uruchomienie aplikacji (`main.py`)**
```python
self.generator = GeneratorFactory.default_bruteforce(min_len=4, max_len=7)
```
- **Abstract Factory** → wywołuje **Builder** wewnętrznie  
- **Builder** → konstruuje `PasswordGenerator(strategy=BruteForceStrategy)`  
- `self.strategy = self.generator.strategy` → dostęp do strategii

> **Pośrednie wywołanie**: `GeneratorFactory` → `GeneratorBuilder` → `BruteForceStrategy` → `CoreBruteGenerator`

---

### **Krok 2: Dzielenie przestrzeni (paczki)**
```python
batch = self._next_batch()  # wybiera wolny indeks globalny
start_idx = batch * TASK_BATCH_SIZE
batch_gen = self.strategy.generate(start_idx, TASK_BATCH_SIZE)
```
- **Strategy.generate()** → deleguje do `CoreBruteGenerator.generate()`  
- Zwraca **`BatchIterator`** – **Iterator** leniwy  
- Przechodzi po `TASK_BATCH_SIZE = 1_000_000` haseł

> **Iterator** działa **leniwie** → nie ładuje 1M haseł do pamięci naraz  
> **Strategy** ukrywa złożoność konwersji indeks → hasło

---

### **Krok 3: Praca w wątku (`_work_loop`)**
```python
for pwd in batch_gen:
    if sha1(pwd) == target_hash: → FOUND
```
- **Iterator** dostarcza hasła jedno po drugim  
- Wątek może przerwać w dowolnym momencie (`global_stop`)  
- Po zakończeniu paczki → `TASK_DONE` → synchronizacja

> **Iterator + wątki = bezpieczne, skalowalne przetwarzanie strumieniowe**

---

### **Krok 4: Synchronizacja sieciowa (multicast, UDP)**
- Nie dotyczy biblioteki – to **aplikacja**  
- Ale **biblioteka umożliwia** dzielenie przestrzeni dzięki:
  - globalnemu indeksowi (`start_idx`)
  - stałej wielkości paczki (`TASK_BATCH_SIZE`)
  - `total_combinations()` – do oszacowania postępu

---

## **4. Komunikacja między wzorcami – schemat**

```
[main.py]
   ↓ (Abstract Factory)
[GeneratorFactory] → [GeneratorBuilder]
                        ↓
                 [BruteForceStrategy] → [CoreBruteGenerator]
                                                ↓
                                     [BatchIterator] ← (Iterator)
                                                ↓
                                     hasło → sha1 → porównanie
```

- **Abstract Factory + Builder** → tworzą obiekt
- **Strategy** → definiuje zachowanie (`generate`, `total_combinations`)
- **Iterator** → realizuje leniwe przetwarzanie

---

## **5. Czy wszystkie wzorce są używane? – TAK**

| Plik | Wzorzec | Czy używany? | Gdzie? |
|------|--------|-------------|------|
| `factory.py` | **Abstract Factory** | TAK | `main.py` → `GeneratorFactory.default_bruteforce()` |
| `builder.py` | **Builder** | TAK | Wewnątrz `factory.py` |
| `strategies.py` | **Strategy** | TAK | `PasswordGenerator.strategy` |
| `generator.py` | **Iterator** | TAK | `CoreBruteGenerator.BatchIterator`, `PermutationIterator` |
| `alphabet.py` | – | TAK | Wspiera wszystkie |

> **Brak martwego kodu** – każdy plik jest **konieczny** i **używany**

---

## **6. Jak to działa razem? – 3 główne akcje**

| Akcja | Wzorzec | Rola |
|------|--------|------|
| **Dzielenie na paczki** | **Iterator + Strategy** | Stały `TASK_BATCH_SIZE`, globalny indeks, leniwe generowanie |
| **Łamanie hasha** | **Iterator** | Przechodzi po hasłach, porównuje SHA1 |
| **Wątki + sieć** | **aplikacja** | Używa biblioteki jako black-box do pobierania paczek |

> **Biblioteka = silnik matematyczny**  
> **Aplikacja = orkiestrator rozproszony**

---

## **7. Podsumowanie – dlaczego to działa**

1. **Elastyczność**: możesz zmienić alfabet, długość, strategię – bez zmian w `main.py`  
2. **Skalowalność**: 62^7 = ~3.5e12 kombinacji → paczki po 1M → 3.5M paczek → rozproszone  
3. **Bezpieczeństwo pamięci**: **Iterator** → zero alokacji dużych list  
4. **Czytelność**: `GeneratorFactory.default_bruteforce()` → jasne intencje  
5. **Testowalność**: biblioteka bez sieci → łatwe testy jednostkowe

---

## **Werdykt**
> **Wszystkie wzorce są żywe, współpracują, są uzasadnione i kluczowe dla działania systemu.**  
> **Biblioteka jest uniwersalna – aplikacja to tylko jeden z możliwych przypadków użycia.**

--- 
# **Jednostronicowa notatka – CZĘŚĆ 2: Delegowanie, linie kodu, odpowiedzialność biblioteki i wątki**

---

## **1. Delegowanie – gdzie, co, linie kodu (przybliżone)**

| Wzorzec | Plik | Linia | Co się dzieje | Przekazywane |
|--------|------|-------|---------------|---------------|
| **Abstract Factory** | `library/factory.py` | **linia 11** | `default_bruteforce()` → wywołuje **Builder** | `min_len`, `max_len` |
| | | | `GeneratorBuilder().with_default_alphabet().with_length_range(...).build()` | → `PasswordGenerator` |
| | `library/builder.py` | **linia 31** | `build()` → `BruteForceStrategy(...)` → `PasswordGenerator(strategy=...)` | `alphabet`, `min`, `max` |
| **Builder** | `library/builder.py` | **linia 20** | `with_default_alphabet()` → `self._alphabet = Alphabet()` | — |
| | | **linia 24** | `with_length_range()` → walidacja + zapis `min_len`, `max_len` | `min_len`, `max_len` |
| | | **31-36** | `build()` → `BruteForceStrategy(...)` → `PasswordGenerator(...)` | → `CoreBruteGenerator` |
| **Strategy** | `library/strategies.py` | **linia 19** | `BruteForceStrategy.__init__()` → `self._core = CoreBruteGenerator(...)` | `alphabet`, `min_length`, `max_length` |
| | | **linia 32** | `generate()` → `return self._core.generate(...)` | **delegacja** |
| | `library/generator.py` | **linia 33** | `CoreBruteGenerator.generate()` → `return BatchIterator(...)` | `start_idx`, `count` |
| **Iterator** | `library/generator.py` | **linia 53** | `BatchIterator.__next__()` → `_idx_to_password(current)` | `idx` → `str` |
| | | **linia 88** | `PermutationIterator.__next__()` → `self.core._idx_to_password(self.current)` | **bezpośrednia konwersja** |

> **Uwaga**: Linie są orientacyjne – zależą od formatowania.  
> **Kluczowe**: **wszystkie wywołania są łańcuchowe i delegujące** – zero duplikacji logiki.

---

## **2. Odpowiedzialność biblioteki – co robi, a czego NIE**

> **Biblioteka `library/` odpowiada TYLKO za:**
> - Generowanie haseł po **indeksie globalnym**  
> - Konwersję `idx → hasło` (np. `0 → "aaaa"`, `1 → "aaab"`)  
> - Podział przestrzeni na **paczki** (przez `start_idx`, `count`)  
> - Leniwe iterowanie (Iterator)  
> - Konfigurację (Builder, Factory)

> **NIE robi:**
> - Sieci, UDP, multicast  
> - Wątków, synchronizacji  
> - Hashowania, porównywania  
> - Logiki rozproszonej

> **Biblioteka = matematyczny silnik permutacji. Aplikacja = orkiestrator.**

---

## **3. Schemat wątków w `app/main.py` – jak się łączą**

```text
[main thread]
   │
   ├───► [multicast_listener] ◄── UDP multicast (224.0.0.251:50001)
   │        ↑↓ PING, SYNC, HASH_SET
   │
   ├───► [task_listener] ◄────── UDP unicast (TASK_PORT=50002)
   │        ↑↓ TASK_START, TASK_DONE, FOUND
   │
   ├───► [send_ping] ────────► multicast co 3s
   │
   ├───► [send_sync_periodic] ──► multicast co 8s + HASH_SET
   │
   ├───► [cleanup] ───────────► co 5s: usuwa martwe nody
   │
   └───► [work_loop] ─────────► główny worker:
            │
            ├──► _next_batch() → wybiera wolny batch (globalny indeks)
            ├──► strategy.generate(start_idx, 1_000_000) → Iterator
            ├──► for pwd in batch_gen: → hash → porównaj
            └──► TASK_DONE / FOUND → broadcast
```

### **Kluczowe powiązania:**
| Wątek | Zależność od biblioteki |
|-------|-------------------------|
| `work_loop` | **Iterator + Strategy** → paczki |
| `task_listener` | **Iterator** → wie, co to `batch` |
| `cleanup` | **done_batches**, `assigned_batches` → stan z biblioteki |

> **Biblioteka nie wie o wątkach – ale wątki wiedzą, jak używać biblioteki.**

---

## **4. Przepływ danych – od biblioteki do aplikacji**

```text
[GeneratorFactory] 
    ↓ (build)
[PasswordGenerator.strategy] 
    ↓ (generate)
[BatchIterator] ──► hasło → SHA1 → porównanie → FOUND?
    ↑
    └─── indeks globalny (batch * 1_000_000)
```

> **Każda paczka = 1M indeksów = 1M haseł = 1 task w sieci**

---

## **5. Podsumowanie – całość w 3 zdaniach**

1. **Biblioteka generuje hasła po indeksie – nic więcej.**  
2. **Aplikacja dzieli przestrzeń, przydziela paczki, synchronizuje – używa biblioteki jak black-box.**  
3. **Wątki komunikują się przez UDP, ale logika pracy opiera się na Iteratorze i globalnym indeksie z biblioteki.**

---
# **Jednostronicowa notatka – CZĘŚĆ 3: Co robią wątki i pliki? Prosto, jak dla laika**

---

## **1. Co robi każdy wątek? – Proste porównania**

| Wątek | Co robi? | Jakby to było w życiu |
|------|---------|---------------------|
| **`_multicast_listener`** | Słucha „krzyków” w sieci (multicast) – kto żyje, co wie, co robi | **Radio CB** – każdy nadaje na jednym kanale: „Tu Janek, żyję!”, „Tu Ania, skończyłam paczkę 5!” |
| **`_task_listener`** | Odbiera bezpośrednie wiadomości (unicast) – „Zaczynam paczkę 10”, „Skończyłem 10”, „ZNALAZŁEM HASŁO!” | **SMS-y od kolegów** – „Hej, biorę zadanie 10”, „Zrobiłem”, „MAM TO!” |
| **`_send_ping`** | Co 3 sekundy krzyczy: „JESTEM ŻYWY!” | **Miganie światłem co 3 sekundy** – „Tu jestem, nie zgasłem!” |
| **`_send_sync_periodic`** | Co 8 sekund mówi: „Zrobiłem paczki: 1,3,7” + „Hasło to: abc123” | **Tablica w biurze** – „Co już zrobione? Jakie hasło szukamy?” |
| **`_cleanup`** | Co 5 sekund sprząta: „Kto nie odpowiada 30 sekund? Usuń go z listy.” | **Sprzątaczka w biurze** – „Kto nie był 30 sekund? Wyrzuć z listy pracowników!” |
| **`_work_loop`** | **Główny robotnik** – bierze paczkę, sprawdza milion haseł, mówi „zrobiłem” lub „Znalazłem!” | **Robotnik na taśmie** – „Biorę 1 mln śrubek, sprawdzam każdą, czy pasuje do dziurki” |

> **Wszystkie wątki działają równolegle – jak kilka osób w jednym pokoju, każdy robi swoje.**

---

## **2. Co robią pliki w bibliotece? – Jak dla babci**

| Plik | Co robi? | Prosty przykład |
|------|--------|----------------|
| **`alphabet.py`** | Tworzy „alfabet” – listę dozwolonych literek | Jakbyś miał klocki LEGO: tylko literki A-Z, a-z, 0-9 – żadnych gwiazdek, kropek |
| **`builder.py`** | **Krok po kroku buduje maszynę do haseł** | Jak budowanie roweru: najpierw koła, potem rama, kierownica → na końcu gotowy rower |
| **`factory.py`** | **Szybko daje gotową maszynę** – nie musisz budować krok po kroku | Jak kupno gotowego roweru w sklepie: „Daj mi rower na 4-7 literki” → bum, masz |
| **`generator.py`** | **Właściwa maszyna** – zamienia numer na hasło | Wpisz numer `0` → dostajesz „aaaa”<br>Wpisz `1` → „aaab” |
| **`strategies.py`** | Mówi maszynie: „Używaj tej metody” | Jak pilot do TV: „Używaj kanału 1” – tu: „Używaj metody brute-force” |

---

## **3. Jak to działa razem? – Historia z życia**

Wyobraź sobie **fabrykę haseł**:

1. **Szef (main.py)** mówi:  
   > „Musimy złamać hasło! Użyjemy maszyny z fabryki!”

2. **Idzie do sklepu (factory.py)** i mówi:  
   > „Daj mi maszynę na hasła 4-7 liter, tylko litery i cyfry.”

3. **Sklep (factory.py)** dzwoni do **budowniczego (builder.py)**:  
   > „Zbuduj maszynę: alfabet = a-zA-Z0-9, długość 4-7.”

4. **Budowniczy** ustawia:  
   - Klocki: tylko dozwolone literki  
   - Długość: od 4 do 7  
   - Metoda: „sprawdzaj po kolei” (strategy)

5. **Maszyna (generator.py)** działa:  
   - Wpisz numer `1000` → dostajesz hasło `abcd`  
   - Działa leniwie – nie robi wszystkich naraz, tylko jedno po drugim

6. **Szef dzieli pracę**:  
   > „Ty bierzesz paczkę 0 (1 mln haseł), ty paczkę 1…”  
   > Każdy robotnik sprawdza swoją paczkę.

7. **Gdy ktoś znajdzie hasło** → krzyczy: „ZNALAZŁEM!” → wszyscy przestają.

---

## **4. Podsumowanie – 3 zdania dla laika**

**Opis**

Iterator daje hasła po kolei — jak taśma z klockami.
Szef (main.py) decyduje: „Ty bierzesz klocki 0–1M, ty 1M–2M” — to on dzieli pracę.
Iterator nie wie, kto pracuje — tylko podaje hasło po numerze.
Szef musi pilnować, by nikt nie brał tej samej paczki — dlatego on przydziela.
Iterator = maszyna do haseł. Szef = kierownik zmianowy.


1. **Biblioteka to fabryka maszyn do haseł – buduje, konfiguruje, generuje po numerze.**  
2. **Aplikacja to szef + robotnicy – dzieli pracę, pilnuje, kto żyje, kto skończył.**  
3. **Wątki to różne osoby w biurze: jeden słucha radia, drugi czyta SMS-y, trzeci sprząta.**

---