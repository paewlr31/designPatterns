"""
strategies.py
-------------
Wzorce Strategy dla:
  * generowania kolejnych kandydatów (BruteForceStrategy, DictionaryStrategy, MaskStrategy)
  * podziału przestrzeni zadań (FixedChunkStrategy, AdaptiveChunkStrategy)
"""

from __future__ import annotations
from typing import Iterable, Iterator, List, Tuple
import itertools
import heapq
import string

# ----------------------------------------------------------------------
#  Strategie generowania kandydatów
# ----------------------------------------------------------------------
class GenerationStrategy:
    """Interfejs dla strategii generowania kolejnych haseł."""

    def candidates(self, start: int, count: int) -> Iterator[str]:
        """Zwraca iterator po `count` kandydatach zaczynając od indeksu `start`."""
        raise NotImplementedError


class BruteForceStrategy(GenerationStrategy):
    """Klasyczna siła-brute – wszystkie kombinacje z podanego alfabetu."""

    def __init__(self, charset: str, length: int):
        self.charset = charset
        self.length = length
        self.base = len(charset)

    def _index_to_password(self, idx: int) -> str:
        pwd = ""
        x = idx
        for _ in range(self.length):
            pwd = self.charset[x % self.base] + pwd
            x //= self.base
        return pwd

    def candidates(self, start: int, count: int) -> Iterator[str]:
        for i in range(count):
            idx = start + i
            yield self._index_to_password(idx)


class DictionaryStrategy(GenerationStrategy):
    """Strategia oparta na liście słów (słownik)."""

    def __init__(self, words: List[str]):
        self.words = words

    def candidates(self, start: int, count: int) -> Iterator[str]:
        end = start + count
        for word in self.words[start:end]:
            yield word


class MaskStrategy(GenerationStrategy):
    """Generowanie wg maski, np. ?l?l?d?d gdzie ?l=litera, ?d=cyfra."""

    _PLACEHOLDERS = {
        'l': string.ascii_lowercase,
        'u': string.ascii_uppercase,
        'd': string.digits,
        's': string.punctuation,
        'a': string.ascii_letters + string.digits,
    }

    def __init__(self, mask: str):
        self.mask = mask
        self.choices = [self._PLACEHOLDERS[c] for c in mask if c in self._PLACEHOLDERS]
        self.positions = [i for i, c in enumerate(mask) if c in self._PLACEHOLDERS]

    def candidates(self, start: int, count: int) -> Iterator[str]:
        total = len(self.choices[0]) ** len(self.choices) if self.choices else 1
        for idx in range(start, min(start + count, total)):
            pwd = list(self.mask)
            x = idx
            for pos, chars in zip(reversed(self.positions), reversed(self.choices)):
                pwd[pos] = chars[x % len(chars)]
                x //= len(chars)
            yield "".join(pwd)


# ----------------------------------------------------------------------
#  Strategie podziału przestrzeni
# ----------------------------------------------------------------------
class ChunkStrategy:
    """Interfejs dla strategii przydzielania fragmentów pracy."""

    def split(self, total: int, workers: int) -> List[Tuple[int, int]]:
        """
        Podziel przestrzeń `total` elementów na `workers` fragmentów.
        Zwraca listę krotek (start_idx, count).
        """
        raise NotImplementedError


class FixedChunkStrategy(ChunkStrategy):
    """Stały rozmiar paczki – każdy worker dostaje `chunk_size` elementów."""

    def __init__(self, chunk_size: int):
        self.chunk_size = chunk_size

    def split(self, total: int, workers: int) -> List[Tuple[int, int]]:
        chunks = []
        start = 0
        for _ in range(workers):
            count = min(self.chunk_size, total - start)
            if count <= 0:
                break
            chunks.append((start, count))
            start += count
        return chunks


class AdaptiveChunkStrategy(ChunkStrategy):
    """
    Adaptacyjny podział – większe paczki dla wolniejszych workerów
    (na podstawie historii czasów). Tutaj prosty podział równy.
    """

    def split(self, total: int, workers: int) -> List[Tuple[int, int]]:
        chunk = total // workers
        remainder = total % workers
        chunks = []
        start = 0
        for i in range(workers):
            extra = 1 if i < remainder else 0
            count = chunk + extra
            if count > 0:
                chunks.append((start, count))
                start += count
        return chunks