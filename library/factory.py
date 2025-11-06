"""
factory.py
----------
Abstract Factory – dostarcza gotowe rodziny generatorów
(BruteForce, Dictionary, Mask) z domyślnymi ustawieniami.
"""

from __future__ import annotations
from .builder import GeneratorBuilder
from .generator import PermutationGenerator
from typing import List


class GeneratorFactory:
    """Statyczna fabryka – wygodne „jednolinijkowe” tworzenie generatorów."""

    @staticmethod
    def brute_force(charset: str, length: int, chunk_size: int = 1_000_000) -> PermutationGenerator:
        return (
            GeneratorBuilder()
            .with_brute_force(charset, length)
            .with_fixed_chunk(chunk_size)
            .build()
        )

    @staticmethod
    def dictionary(words: List[str], chunk_size: int = 1_000_000) -> PermutationGenerator:
        return (
            GeneratorBuilder()
            .with_dictionary(words)
            .with_fixed_chunk(chunk_size)
            .build()
        )

    @staticmethod
    def mask(mask: str, chunk_size: int = 1_000_000) -> PermutationGenerator:
        return (
            GeneratorBuilder()
            .with_mask(mask)
            .with_fixed_chunk(chunk_size)
            .build()
        )