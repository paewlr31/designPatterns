from __future__ import annotations
from typing import Iterator, Optional
from .alphabet import Alphabet


class CoreBruteGenerator:
    """
    Niski poziom generatora, który rzeczywiście konwertuje indeksy
    na hasła i udostępnia iteratory (BatchIterator) do iteracji po kombinacjach.
    """

    def __init__(self, alphabet: Alphabet, min_length: int, max_length: int):
        self.alphabet = alphabet
        self.min_length = min_length
        self.max_length = max_length
        # precompute counts per length
        self._lengths = list(range(self.min_length, self.max_length + 1))
        self._counts = [alphabet.base ** L for L in self._lengths]
        self._total = sum(self._counts)

    def total_combinations(self, min_len: int = None, max_len: int = None) -> int:
        # parametry min_len/max_len są ignorowane — generator ma ustawiony swój zakres
        return self._total

    def _idx_to_password(self, idx: int) -> str:
        offset = idx
        for L, cnt in zip(self._lengths, self._counts):
            if offset < cnt:
                x = offset
                pwd_chars = []
                for _ in range(L):
                    pwd_chars.append(self.alphabet[x % self.alphabet.base])
                    x //= self.alphabet.base
                return "".join(reversed(pwd_chars))
            offset -= cnt
        raise IndexError("Indeks poza zakresem generatora")

    class BatchIterator:
        """
        Prawdziwy iterator zwracany przez CoreBruteGenerator.generate().
        Trzyma referencję do generatora i iteruje od start_idx przez 'count' elementów
        (lub do końca przestrzeni).
        """

        def __init__(self, core: "CoreBruteGenerator", start_idx: int, count: int):
            self._core = core
            self._current = int(start_idx)
            self._end = min(self._current + int(count), core._total)

        def __iter__(self) -> "CoreBruteGenerator.BatchIterator":
            return self

        def __next__(self) -> str:
            if self._current >= self._end:
                raise StopIteration
            pwd = self._core._idx_to_password(self._current)
            self._current += 1
            return pwd

    def generate(self, start_idx: int, count: int) -> Iterator[str]:
        """
        Zwraca instancję BatchIterator — prawdziwy obiekt iteratora,
        który leniwie zwraca kolejne hasła zaczynając od start_idx.
        """
        # Zwracamy BatchIterator zamiast anonimowego generatora
        return CoreBruteGenerator.BatchIterator(self, start_idx, count)


class PermutationIterator:
    """
    Wrapper iteratora nad CoreBruteGenerator — zachowuje kompatybilność z API maina.
    Implementacja zoptymalizowana: nie tworzy nowego generatora przy każdym __next__(),
    tylko bezpośrednio używa _idx_to_password, co eliminuje nadmiarowy overhead.
    """

    def __init__(self, core_generator: CoreBruteGenerator, start_idx: int = 0, batch_size: int = 1_000_000):
        self.core = core_generator
        self.current = int(start_idx)
        self.batch_size = int(batch_size)
        self._total = self.core.total_combinations()
        # Nie tworzymy wewnętrznego generatora dla pojedynczych elementów,
        # ale możemy wygodnie pobrać większe batch'e przez get_batch().
        self._closed = False

    def __iter__(self) -> "PermutationIterator":
        return self

    def __next__(self) -> str:
        if self._closed:
            raise StopIteration
        if self.current >= self._total:
            self._closed = True
            raise StopIteration
        # Bezpośrednie wywołanie konwersji indeks -> password (wydajne)
        pwd = self.core._idx_to_password(self.current)
        self.current += 1
        return pwd

    def skip_to(self, idx: int):
        """Przeskocz do konkretnego indeksu."""
        if idx < 0:
            raise ValueError("idx must be >= 0")
        if idx >= self._total:
            raise IndexError("skip_to: idx poza zakresem")
        self.current = int(idx)
        self._closed = False

    def get_batch(self, size: int) -> Iterator[str]:
        """
        Pobierz paczkę haseł (leniwy iterator) zaczynając od aktualnego indeksu.
        Zwracany iterator (BatchIterator) będzie niezależny — nie zmienia automatycznie
        self.current; jeżeli chcesz przesunąć stan PermutationIteratora, zrób to ręcznie.
        """
        # Zwracamy BatchIterator który zaczyna od self.current i ma 'size' elementów.
        # Uwaga: Caller może chcieć zaktualizować self.current po iteracji.
        return self.core.generate(self.current, size)


class PasswordGenerator:
    """
    Wyższy poziom wrapper: trzyma CoreBruteGenerator i wystawia
    API wymagane przez main:
      - .strategy (obiekt ze generate/total_combinations) <- tu self
      - generate(start_idx, count)
      - total_combinations()
      - iterator(...)
    Dzięki temu main może robić `self.generator.strategy.generate(...)` tak jak wcześniej.
    """

    def __init__(self, core_generator: CoreBruteGenerator):
        self.core = core_generator
        # main oczekuje atrybutu `strategy` — ustawiamy go jako alias do siebie
        self.strategy = self

    # --- API strategii ---
    def generate(self, start_idx: int, count: int) -> Iterator[str]:
        # Delegujemy do CoreBruteGenerator, który teraz zwraca BatchIterator (prawdziwy iterator)
        return self.core.generate(start_idx, count)

    def total_combinations(self, min_len: int = None, max_len: int = None) -> int:
        return self.core.total_combinations(min_len, max_len)

    # --- convenience ---
    def iterator(self, start_idx: int = 0, batch_size: int = 1_000_000) -> PermutationIterator:
        return PermutationIterator(self.core, start_idx, batch_size)
