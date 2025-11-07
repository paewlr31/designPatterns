from __future__ import annotations
from typing import Protocol, Iterator, Tuple, List
from .alphabet import Alphabet


class GenerationStrategy(Protocol):
    """Protokół strategii generowania haseł."""
    
    def generate(self, start_idx: int, count: int) -> Iterator[str]:
        """Generuje count haseł zaczynając od globalnego indeksu start_idx."""
        ...

    def total_combinations(self, min_len: int, max_len: int) -> int:
        """Zwraca całkowitą liczbę kombinacji dla podanych długości."""
        ...


class BruteForceStrategy:
    """Pełne przeszukiwanie dla stałych długości."""
    
    def __init__(self, alphabet: Alphabet, min_length: int, max_length: int):
        self.alphabet = alphabet
        self.min_length = min_length
        self.max_length = max_length
        self._lengths = list(range(min_length, max_length + 1))
        self._counts = [alphabet.base ** L for L in self._lengths]
        self._total = sum(self._counts)

    def total_combinations(self, min_len: int, max_len: int) -> int:
        return self._total

    def _idx_to_password(self, idx: int) -> str:
        offset = idx
        for L, cnt in zip(self._lengths, self._counts):
            if offset < cnt:
                x = offset
                pwd = []
                for _ in range(L):
                    pwd.append(self.alphabet[x % self.alphabet.base])
                    x //= self.alphabet.base
                return "".join(reversed(pwd))
            offset -= cnt
        raise IndexError("Indeks poza zakresem")

    def generate(self, start_idx: int, count: int) -> Iterator[str]:
        end_idx = start_idx + count
        for idx in range(start_idx, min(end_idx, self._total)):
            yield self._idx_to_password(idx)