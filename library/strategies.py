# library/strategies.py
from typing import Protocol, Iterator, List
from .alphabet import ALPHABET

class CandidateStrategy(Protocol):
    def generate(self, length: int) -> Iterator[str]:
        """Zwraca iterator po kandydatach (leniwie)"""
        ...

class ChunkStrategy(Protocol):
    def split(self, total: int, workers: int) -> List[tuple[int, int]]:
        """Dzieli przestrzeń na chunk'i: (start, end)"""
        ...

# === STRATEGIE GENEROWANIA ===

class BruteForceStrategy:
    def generate(self, length: int) -> Iterator[str]:
        """Generuje wszystkie 62^length kombinacji (leniwie)"""
        from itertools import product
        yield from (''.join(combo) for combo in product(ALPHABET, repeat=length))

class DictionaryStrategy:
    def __init__(self, words: List[str]):
        self.words = [w for w in words if len(w) == 4]
    
    def generate(self, length: int) -> Iterator[str]:
        yield from self.words

# === STRATEGIE PODZIAŁU ===

class FixedChunkStrategy:
    def __init__(self, chunk_size: int):
        self.chunk_size = chunk_size
    
    def split(self, total: int, workers: int) -> List[tuple[int, int]]:
        chunks = []
        start = 0
        while start < total:
            end = min(start + self.chunk_size, total)
            chunks.append((start, end))
            start = end
        return chunks

class AdaptiveChunkStrategy:
    def split(self, total: int, workers: int) -> List[tuple[int, int]]:
        chunk_size = total // workers
        remainder = total % workers
        chunks = []
        start = 0
        for i in range(workers):
            extra = 1 if i < remainder else 0
            end = start + chunk_size + extra
            chunks.append((start, min(end, total)))
            start = end
        return chunks