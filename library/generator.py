"""
generator.py
------------
Klasa PermutationGenerator – iterator leniwe generujący kandydatów
z wybraną strategią generowania i opcjonalnym podziałem przestrzeni.
"""

from __future__ import annotations
from typing import Iterator, Optional
from .strategies import GenerationStrategy, ChunkStrategy, FixedChunkStrategy


class PermutationGenerator:
    """
    Leniwy iterator po kandydatach.
    Umożliwia podział pracy na wiele workerów (chunk strategy).
    """

    def __init__(
        self,
        strategy: GenerationStrategy,
        total: Optional[int] = None,
        chunk_strategy: Optional[ChunkStrategy] = None,
    ):
        self.strategy = strategy
        self.total = total or self._estimate_total()
        self.chunk_strategy = chunk_strategy or FixedChunkStrategy(1_000_000)

        self._current_start = 0
        self._current_count = 0
        self._exhausted = False

    # ------------------------------------------------------------------
    #  Pomocnicze
    # ------------------------------------------------------------------
    def _estimate_total(self) -> int:
        """Próba oszacowania rozmiaru przestrzeni (jeśli nie podano)."""
        # Dla BruteForceStrategy możemy obliczyć dokładnie
        if hasattr(self.strategy, "base") and hasattr(self.strategy, "length"):
            return self.strategy.base ** self.strategy.length
        return 0  # nieznane – będziemy iterować do wyczerpania

    # ------------------------------------------------------------------
    #  API publiczne
    # ------------------------------------------------------------------
    def next_chunk(self, worker_id: int, workers: int) -> Iterator[str]:
        """
        Zwraca iterator po kolejnej paczce dla danego workera.
        Po wyczerpaniu przestrzeni zwraca pusty iterator.
        """
        if self._exhausted:
            return iter(())

        chunks = self.chunk_strategy.split(self.total, workers)
        if worker_id >= len(chunks):
            self._exhausted = True
            return iter(())

        start, count = chunks[worker_id]
        # przesunięcie względem już przetworzonych chunków
        start += self._current_start

        if start >= self.total:
            self._exhausted = True
            return iter(())

        count = min(count, self.total - start)
        self._current_start += count
        if self._current_start >= self.total:
            self._exhausted = True

        return self.strategy.candidates(start, count)

    def __iter__(self) -> Iterator[str]:
        """Cała przestrzeń jako jeden iterator (bez podziału)."""
        return self.strategy.candidates(0, self.total)

    # ------------------------------------------------------------------
    #  Kontekst manager – przydatne przy pracy w pętli
    # ------------------------------------------------------------------
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass