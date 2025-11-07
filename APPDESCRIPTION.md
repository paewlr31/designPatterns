**NOTATKA: WZORCE PROJEKTOWE W TWOIM PROJEKCIE – GDZIE, JAK, DLACZEGO, CO SIĘ PRZEKAZUJE**

---

## WPROWADZENIE

Masz **bibliotekę** (`library/`) i **aplikację demonstracyjną** (`app/main.py`).  
Biblioteka **generuje hasła** (permutacje).  
Aplikacja **łamie hashe rozproszone** – używa biblioteki do generowania kandydatów.

**Użyto 4 wzorców**:
1. **Strategy**
2. **Iterator**
3. **Builder**
4. **Abstract Factory**

**Wszystkie są używane** – **bezpośrednio lub pośrednio** – przez aplikację.

---

## 1. STRATEGY – BEZPOŚREDNIO UŻYWANY

| Gdzie? | Co robi? | Dlaczego? | Jak? |
|-------|--------|---------|-----|
| `library/strategies.py` → `BruteForceStrategy` | Definiuje **algorytm generowania haseł** | Żeby można było wymienić: brute-force → maska → słownik | Implementuje `generate(start_idx, count)` |

### **Użycie w `main.py` – BEZPOŚREDNIO**

```python
# Linia w __init__():
self.strategy = self.generator.strategy   # <--- STRATEGY

# Linia w _process_batch():
batch_gen = self.strategy.generate(start_idx, TASK_BATCH_SIZE)  # <--- STRATEGY!
```

**Co się przekazuje?**  
`self.strategy` to obiekt `BruteForceStrategy` – aplikacja **bezpośrednio wywołuje jego metodę `generate()`**.

**Dlaczego?**  
Bo aplikacja **nie musi wiedzieć**, że to brute-force. Może być dowolna strategia – wystarczy, że ma `.generate()`.

---

## 2. ITERATOR – POŚREDNIO UŻYWANY (przez Strategy)

| Gdzie? | Co robi? | Dlaczego? | Jak? |
|-------|--------|---------|-----|
| `library/generator.py` → `PermutationIterator` | Leniwe generowanie haseł | 62⁷ = 3.5 mld → nie da się w pamięci | `__next__()` zwraca jedno hasło |

### **Użycie w `main.py` – POŚREDNIO**

```python
for pwd in batch_gen:  # <--- batch_gen to iterator!
    if hashlib.sha1(pwd.encode()) == target_hash:
        return pwd
```

**Co się przekazuje?**  
`self.strategy.generate(...)` **zwraca iterator** (generator), który **używa wewnętrznie `PermutationIterator`**.

**Dlaczego?**  
Bo `generate()` zwraca `yield` → to **iterator**. Aplikacja **nie wie**, że istnieje `PermutationIterator`, ale **korzysta z jego właściwości**.

---

## 3. BUILDER – POŚREDNIO UŻYWANY (przez Factory)

| Gdzie? | Co robi? | Dlaczego? | Jak? |
|-------|--------|---------|-----|
| `library/builder.py` → `GeneratorBuilder` | Krok po kroku konfiguruje generator | Zamiast 10 parametrów w konstruktorze | `.with_...().build()` |

### **Użycie w `main.py` – POŚREDNIO (przez Factory)**

```python
# Linia w __init__():
self.generator = GeneratorFactory.default_bruteforce(min_len=4, max_len=7)
```

**Co się dzieje pod spodem?**

```python
# W factory.py
@staticmethod
def default_bruteforce(...):
    return (
        GeneratorBuilder()               # <--- BUILDER!
        .with_default_alphabet()         # <--- konfiguracja
        .with_length_range(min_len, max_len)
        .build()                         # <--- zwraca PasswordGenerator
    )
```

**Co się przekazuje?**  
`GeneratorFactory` → **używa `GeneratorBuilder`** → zwraca `PasswordGenerator`.

**Dlaczego?**  
Aplikacja **nie musi znać `Builder`**, ale **korzysta z jego efektu** – gotowego, skonfigurowanego generatora.

---

## 4. ABSTRACT FACTORY – BEZPOŚREDNIO UŻYWANY

| Gdzie? | Co robi? | Dlaczego? | Jak? |
|-------|--------|---------|-----|
| `library/factory.py` → `GeneratorFactory` | Tworzy gotowe generatory | Ukrywa złożoność (Builder + Strategy) | `default_bruteforce()` |

### **Użycie w `main.py` – BEZPOŚREDNIO**

```python
from library.factory import GeneratorFactory   # <--- FACTORY

self.generator = GeneratorFactory.default_bruteforce(...)  # <--- FACTORY!
```

**Co się przekazuje?**  
`GeneratorFactory` → zwraca `PasswordGenerator` (z `BruteForceStrategy` i `Alphabet`).

**Dlaczego?**  
Aplikacja **nie musi wiedzieć**:
- Jakiego alfabetu użyć
- Jakich długości
- Jak zbudować strategię  
→ **dostaje gotowy obiekt**.

---

## SCHEMAT PRZEPŁYWU DANYCH

```
app/main.py
      │
      ├── używa GeneratorFactory.default_bruteforce()  ←── (Abstract Factory)
      │         │
      │         └── wywołuje GeneratorBuilder()       ←── (Builder)
      │                   │
      │                   └── tworzy BruteForceStrategy ←── (Strategy)
      │                             │
      │                             └── zwraca PasswordGenerator
      │
      └── self.generator.strategy → generate() → zwraca iterator ←── (Iterator)
                 │
                 └── for pwd in batch_gen: → sprawdza hash
```

---

## TABELA PODSUMOWUJĄCA

| Wzorzec | Gdzie w bibliotece? | Gdzie w `main.py`? | Bezpośrednio / Pośrednio? | Co się przekazuje? |
|--------|---------------------|--------------------|---------------------------|---------------------|
| **Strategy** | `strategies.py` | `self.strategy.generate()` | **BEZPOŚREDNIO** | Obiekt strategii |
| **Iterator** | `generator.py` | `for pwd in batch_gen` | **POŚREDNIO** | Generator (iterator) |
| **Builder** | `builder.py` | — (ukryty w Factory) | **POŚREDNIO** | Konfiguracja |
| **Abstract Factory** | `factory.py` | `GeneratorFactory.default_...` | **BEZPOŚREDNIO** | Gotowy generator |

---

## DLACZEGO TAK ZROBIONE?

| Problem | Rozwiązanie | Korzyść |
|--------|------------|--------|
| **Złożona konfiguracja** | `Builder` + `Factory` | Czytelny kod, brak 10-argumentowych konstruktorów |
| **Różne algorytmy** | `Strategy` | Łatwo dodać `MaskStrategy`, `DictionaryStrategy` |
| **Ogromna przestrzeń** | `Iterator` | Brak wyczerpania pamięci |
| **Aplikacja nie powinna wiedzieć szczegółów** | `Factory` | Aplikacja = prosty klient |

---

## CO MOŻNA ZMIENIĆ BEZ DOTYKANIA `main.py`?

```python
# W factory.py
@staticmethod
def with_mask(mask: str):
    return GeneratorBuilder().with_mask(mask).build()  # nowa strategia!
```

→ `main.py` dalej działa: `GeneratorFactory.with_mask("?l?l?d")`

---

## PODSUMOWANIE W 3 PUNKTACH

1. **Aplikacja używa `Factory` → dostaje gotowy generator**  
2. **Generator ma `Strategy` → aplikacja wywołuje `.generate()`**  
3. **`generate()` zwraca `iterator` → hasła są generowane leniwie**

**Wszystkie wzorce są użyte – 2 bezpośrednio, 2 pośrednio.**  
**Biblioteka jest elastyczna, aplikacja prosta.**

---

**Chcesz wersję z `MaskStrategy` albo `DictionaryStrategy`?**  
Mogę dodać w 5 minut – i pokazać, jak `main.py` **nawet nie drgnie**.