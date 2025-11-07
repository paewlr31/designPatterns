from __future__ import annotations
from typing import Iterator, Protocol
from .alphabet import Alphabet
from .generator import CoreBruteGenerator


class GenerationStrategy(Protocol):
    """Protokół strategii generowania haseł."""

    def generate(self, start_idx: int, count: int) -> Iterator[str]:
        """Generuje count haseł zaczynając od globalnego indeksu start_idx."""
        ...

    def total_combinations(self, min_len: int, max_len: int) -> int:
        """Zwraca całkowitą liczbę kombinacji dla podanych długości."""
        ...


class BruteForceStrategy:
    """
    Adapter-strategia, która deleguje pracę do CoreBruteGenerator.
    Zostało tak napisane, żeby kod, który importuje 'BruteForceStrategy'
    dalej działał — ale ciężka praca wykonuje się w CoreBruteGenerator.
    """

    def __init__(self, alphabet: Alphabet, min_length: int, max_length: int):
        self._core = CoreBruteGenerator(alphabet, min_length, max_length)

    def total_combinations(self, min_len: int = None, max_len: int = None) -> int:
        return self._core.total_combinations(min_len, max_len)

    def generate(self, start_idx: int, count: int) -> Iterator[str]:
        return self._core.generate(start_idx, count)
