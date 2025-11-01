# library/builder.py
from typing import List, Optional
from .strategies import (
    BruteForceStrategy, DictionaryStrategy,
    FixedChunkStrategy, AdaptiveChunkStrategy,
    CandidateStrategy, ChunkStrategy
)
from .generator import PasswordIterator

class PasswordGeneratorBuilder:
    def __init__(self):
        self._length = 4
        self._candidate_strategy: Optional[CandidateStrategy] = None
        self._chunk_strategy: Optional[ChunkStrategy] = None
        self._dictionary: List[str] = []

    def with_length(self, length: int) -> 'PasswordGeneratorBuilder':
        self._length = length
        return self

    def with_bruteforce(self) -> 'PasswordGeneratorBuilder':
        self._candidate_strategy = BruteForceStrategy()
        return self

    def with_dictionary(self, words: List[str]) -> 'PasswordGeneratorBuilder':
        self._candidate_strategy = DictionaryStrategy(words)
        self._dictionary = words
        return self

    def with_fixed_chunks(self, chunk_size: int) -> 'PasswordGeneratorBuilder':
        self._chunk_strategy = FixedChunkStrategy(chunk_size)
        return self

    def with_adaptive_chunks(self) -> 'PasswordGeneratorBuilder':
        self._chunk_strategy = AdaptiveChunkStrategy()
        return self

    def build_iterator(self, start: int = 0, end: int = None) -> PasswordIterator:
        if self._candidate_strategy is None:
            self.with_bruteforce()
        if self._chunk_strategy is None:
            self.with_adaptive_chunks()
        return PasswordIterator(self._candidate_strategy, self._length, start, end)

    def build_full_space_size(self) -> int:
        return 62 ** self._length