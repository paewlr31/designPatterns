from __future__ import annotations
from typing import Iterator, Optional
from .strategies import GenerationStrategy, BruteForceStrategy
from .alphabet import Alphabet


class PermutationIterator:
    """Leniwy iterator po hasłach z danej strategii."""
    
    def __init__(self, strategy: GenerationStrategy, start_idx: int, batch_size: int = 1000000):
        self.strategy = strategy
        self.start_idx = start_idx
        self.batch_size = batch_size
        self.current = start_idx

    def __iter__(self) -> Iterator[str]:
        return self

    def __next__(self) -> str:
        if self.current >= self.strategy.total_combinations(0, 999):  # dummy, realnie w strategii
            raise StopIteration
        pwd = next(self.strategy.generate(self.current, 1))
        self.current += 1
        return pwd

    def skip_to(self, idx: int):
        """Przeskocz do konkretnego indeksu."""
        self.current = idx

    def get_batch(self, size: int) -> Iterator[str]:
        """Pobierz paczkę haseł."""
        return self.strategy.generate(self.current, size)


class PasswordGenerator:
    """Główny generator haseł oparty na strategii."""
    
    def __init__(self, strategy: GenerationStrategy):
        self.strategy = strategy

    def iterator(self, start_idx: int = 0, batch_size: int = 1000000) -> PermutationIterator:
        return PermutationIterator(self.strategy, start_idx, batch_size)

    def total_combinations(self) -> int:
        return self.strategy.total_combinations(0, 999)  # dummy — realnie w strategii