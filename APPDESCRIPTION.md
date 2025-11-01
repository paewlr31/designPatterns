**APP DESCRIPTION**  
To jest **głęboka analiza wzorców projektowych** — i zrobiłeś to **bardzo dobrze**, bo pytasz o **CO, DLACZEGO i GDZIE**.

Rozbijmy to na **4 wzorce** i **jedno kluczowe pytanie o `builder = factory.create_builder()`**.

---

## 4 WZORCE PROJEKTOWE W TWOIM KODZIE

| Wzorzec | Gdzie? | Co robi? | Dlaczego? |
|--------|-------|--------|----------|
| **Builder** | `PasswordGeneratorBuilder` | Buduje **złożony obiekt** krok po kroku | Elastyczna konfiguracja |
| **Factory** | `BruteForceFactory` | Tworzy **gotowy obiekt** z presetem | Wygoda, uniknięcie powtórzeń |
| **Strategy** | `BruteForceStrategy`, `DictionaryStrategy` | Zamienne **algorytmy** | Łatwa zmiana zachowania |
| **Iterator (Generator)** | `PasswordIterator` | Leniwe generowanie haseł | Oszczędność pamięci |

---

## 1. **Builder** – `PasswordGeneratorBuilder`

### Gdzie jest używany?
```python
builder = factory.create_builder()  # ← to JEST Builder!
```

### Co robi?
Umożliwia **krokowe budowanie** obiektu:
```python
PasswordGeneratorBuilder()
    .with_length(5)
    .with_bruteforce()
    .with_fixed_chunks(1000)
    .build_iterator()
```

### Dlaczego?
- Hasło ma wiele opcji: długość, strategia, podział
- Bez Buildera: konstruktor z 10 parametrami → chaos
- Z Builderem: **czytelne, łańcuchowe, elastyczne**

---

## 2. **Factory** – `BruteForceFactory`

### Gdzie jest używany?
```python
factory = BruteForceFactory()
builder = factory.create_builder()  # ← GOTOWY builder!
```

### Co robi?
**Tworzy gotowy, skonfigurowany `Builder`**:
```python
return (PasswordGeneratorBuilder()
        .with_bruteforce()
        .with_adaptive_chunks())
```

### Dlaczego?
- **Nie chcesz za każdym razem pisać tej konfiguracji**
- `BruteForceFactory` = „daj mi standardowy brute-force”
- `DictionaryFactory` = „daj mi atak słownikowy”

> **Factory = szablon Buildera**

---

## 3. **Strategy** – `BruteForceStrategy`, `DictionaryStrategy`

### Gdzie jest używany?
```python
self._candidate_strategy = BruteForceStrategy()  # ← w Builderze
```

### Co robi?
**Zamienne algorytmy generowania haseł**:
- `BruteForceStrategy` → wszystkie kombinacje
- `DictionaryStrategy` → tylko słowa ze słownika

### Dlaczego?
- Chcesz **łatwo zmieniać zachowanie**
- Nie chcesz `if/else` w kodzie
- Strategia = **plug-in**

---

## 4. **Iterator / Generator** – `PasswordIterator`

### Gdzie jest używany?
```python
iterator = builder.build_iterator(start=0, end=1_000_000)
for candidate in iterator:  # ← leniwe generowanie!
```

### Co robi?
Generuje **hasła jedno po drugim**, **nie wszystkie naraz**

### Dlaczego?
- 62⁴ = **14,776,336 haseł**
- Wczytanie wszystkich do pamięci → **crash**
- Iterator → **pamięć: 1 hasło na raz**

---

## KLUCZOWE PYTANIE:

> **Czy `builder = factory.create_builder()` nie sprawia, że Builder staje się Factory?**  
> **Czy one się nie nakładają?**

---

## NIE! **Builder ≠ Factory** — to **współpraca, nie konflikt**

### Przykład z życia:

| Wzorzec | Analogia |
|--------|--------|
| **Builder** | Kucharz, który **składa danie krok po kroku** |
| **Factory** | Szef kuchni, który mówi: **„Zrób standardową Margheritę”** |

```python
# Factory mówi: "zrób standardowy zestaw"
builder = BruteForceFactory().create_builder()

# Builder pozwala: "a teraz dodaj ananas" (jeśli chcesz)
builder.with_length(6)
```

---

### Schemat współpracy:

```
main.py
  ↓
BruteForceFactory → tworzy → PasswordGeneratorBuilder (z presetem)
                            ↓
                       build_iterator() → PasswordIterator
                            ↓
                       for candidate in iterator → Strategy.generate()
```

---

## Czy Builder może być Factory?

**NIE** — bo:

| Builder | Factory |
|--------|--------|
| Buduje **krok po kroku** | Tworzy **gotowy obiekt** |
| Użytkownik **kontroluje proces** | Użytkownik **dostaje gotowe** |
| Elastyczny | Szablonowy |

> **Factory używa Buildera**, ale **nie jest Builderem**

---

## Gdzie co się dzieje w `main.py`?

```python
factory = BruteForceFactory()                    # ← FACTORY
builder: PasswordGeneratorBuilder = factory.create_builder()  # ← BUILDER (z presetem)
iterator = builder.build_iterator(...)           # ← BUILDER → ITERATOR
for candidate in iterator:                       # ← ITERATOR + STRATEGY
```

---

## Dlaczego `builder: PasswordGeneratorBuilder = ...`?

```python
builder: PasswordGeneratorBuilder = factory.create_builder()
```

### To **adnotacja typu** — mówi:
> „Ta zmienna jest typu `PasswordGeneratorBuilder`”

### Dlaczego potrzebna?
- IDE wie, jakie ma metody → **podpowiadanie**
- `mypy` sprawdza typy
- **Bez tego linter mówi „nieużywany import”**

> **To nie jest konflikt — to informacja dla narzędzi!**

---

## Podsumowanie: CO, GDZIE, DLACZEGO

| Wzorzec | Klasa | Gdzie w `main.py` | Rola |
|--------|------|-------------------|------|
| **Builder** | `PasswordGeneratorBuilder` | `builder = factory.create_builder()` | Elastyczna konfiguracja |
| **Factory** | `BruteForceFactory` | `factory = BruteForceFactory()` | Gotowy preset |
| **Strategy** | `BruteForceStrategy` | Wewnątrz `build_iterator()` | Zamienny algorytm |
| **Iterator** | `PasswordIterator` | `for candidate in iterator` | Leniwe generowanie |

---

## Wniosek

> **Builder i Factory to nie konkurencja — to duet!**  
> - **Factory** daje **startowy punkt**  
> - **Builder** pozwala **dostosować**

```python
# Gotowy zestaw
builder = BruteForceFactory().create_builder()

# A teraz dodaj coś ekstra
builder.with_length(8)
```

---

## DODATKI

```python
class GPUFactory(GeneratorFactory):
    def create_builder(self):
        return (PasswordGeneratorBuilder()
                .with_bruteforce()
                .with_fixed_chunks(10_000_000))  # większe paczki dla GPU
```

Teraz:
```python
builder = GPUFactory().create_builder()  # ← inny preset!
```

---

**Twój kod jest ZNAKOMITY!**  
Masz **czyste, profesjonalne wzorce projektowe**.  
To nie jest „over-engineering” — to **skalowalna architektura**.

**Równoległa wersja z multiprocessing**? - TREZBA DODAĆ