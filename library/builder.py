"""
builder.py
----------
Builder dla PermutationGenerator – krok po kroku konfiguracja.
"""

from __future__ import annotations
from typing import List, Optional
from .strategies import (
    BruteForceStrategy,
    DictionaryStrategy,
    MaskStrategy,
    FixedChunkStrategy,
    AdaptiveChunkStrategy,
)
from .generator import PermutationGenerator
from .alphabet import ASCII_LETTERS_DIGITS


class GeneratorBuilder:
    """Fluent builder dla PermutationGenerator."""

    def __init__(self):
        self._charset: Optional[str] = None
        self._length: Optional[int] = None
        self._words: Optional[List[str]] = None
        self._mask: Optional[str] = None
        self._chunk_size: int = 1_000_000
        self._adaptive: bool = False

    # ------------------------------------------------------------------
    #  Ustawienia Brute-Force
    # ------------------------------------------------------------------
    def with_brute_force(self, charset: str = ASCII_LETTERS_DIGITS, length: int = 4) -> "GeneratorBuilder":
        self._charset = charset
        self._length = length
        self._words = None
        self._mask = None
        return self

    # ------------------------------------------------------------------
    #  Ustawienia Dictionary
    # ------------------------------------------------------------------
    def with_dictionary(self, words: List[str]) -> "GeneratorBuilder":
        self._words = words
        self._charset = None
        self._length = None
        self._mask = None
        return self

    # ------------------------------------------------------------------
    #  Ustawienia Mask
    # ------------------------------------------------------------------
    def with_mask(self, mask: str) -> "GeneratorBuilder":
        self._mask = mask
        self._charset = None
        self._length = None
        self._words = None
        return self

    # ------------------------------------------------------------------
    #  Chunk (podział)
    # ------------------------------------------------------------------
    def with_fixed_chunk(self, size: int) -> "GeneratorBuilder":
        self._chunk_size = size
        self._adaptive = False
        return self

    def with_adaptive_chunk(self) -> "GeneratorBuilder":
        self._adaptive = True
        return self

    # ------------------------------------------------------------------
    #  Budowanie
    # ------------------------------------------------------------------
    def build(self) -> PermutationGenerator:
        # ---- wybór strategii generowania ----
        if self._charset is not None and self._length is not None:
            gen_strategy = BruteForceStrategy(self._charset, self._length)
            total = len(self._charset) ** self._length
        elif self._words is not None:
            gen_strategy = DictionaryStrategy(self._words)
            total = len(self._words)
        elif self._mask is not None:
            gen_strategy = MaskStrategy(self._mask)
            # dokładna liczba = produkt rozmiarów placeholderów
            total = 1
            for c in self._mask:
                if c in MaskStrategy._PLACEHOLDERS:
                    total *= len(MaskStrategy._PLACEHOLDERS[c])
        else:
            raise ValueError("Nie podano żadnej strategii generowania.")

        # ---- wybór strategii podziału ----
        if self._adaptive:
            chunk_strategy = AdaptiveChunkStrategy()
        else:
            chunk_strategy = FixedChunkStrategy(self._chunk_size)

        return PermutationGenerator(
            strategy=gen_strategy,
            total=total,
            chunk_strategy=chunk_strategy,
        )