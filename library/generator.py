# library/generator.py
from typing import Iterator, Optional
from .strategies import CandidateStrategy

class PasswordIterator:
    """Leniwy iterator po kandydatach – używa strategii"""
    def __init__(self, strategy: CandidateStrategy, length: int, start_idx: int = 0, end_idx: Optional[int] = None):
        self.strategy = strategy
        self.length = length
        self.start_idx = start_idx
        self.end_idx = end_idx
        self._iterator = None
        self._current_idx = 0

    def __iter__(self) -> Iterator[str]:
        self._iterator = self.strategy.generate(self.length)
        # Przeskocz do start_idx
        for _ in range(self.start_idx):
            try:
                next(self._iterator)
            except StopIteration:
                break
            self._current_idx += 1
        return self

    def __next__(self) -> str:
        if self.end_idx is not None and self._current_idx >= self.end_idx:
            raise StopIteration
        candidate = next(self._iterator)
        self._current_idx += 1
        return candidate