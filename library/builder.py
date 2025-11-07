from __future__ import annotations
from typing import Optional
from .alphabet import Alphabet
from .strategies import BruteForceStrategy
from .generator import PasswordGenerator


class GeneratorBuilder:
    """Builder do konfigurowania generatora haseł."""
    
    def __init__(self):
        self._alphabet: Optional[Alphabet] = None
        self._min_length: int = 4
        self._max_length: int = 7

    def with_alphabet(self, charset: str) -> "GeneratorBuilder":
        self._alphabet = Alphabet(charset)
        return self

    def with_default_alphabet(self) -> "GeneratorBuilder":
        self._alphabet = Alphabet()
        return self

    def with_length_range(self, min_len: int, max_len: int) -> "GeneratorBuilder":
        if min_len < 1 or max_len < min_len:
            raise ValueError("Niepoprawne długości")
        self._min_length = min_len
        self._max_length = max_len
        return self

    def build(self) -> PasswordGenerator:
        if not self._alphabet:
            self._alphabet = Alphabet()
        strategy = BruteForceStrategy(
            alphabet=self._alphabet,
            min_length=self._min_length,
            max_length=self._max_length
        )
        return PasswordGenerator(strategy)