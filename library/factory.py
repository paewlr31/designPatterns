from __future__ import annotations
from .builder import GeneratorBuilder
from .generator import PasswordGenerator
from .alphabet import Alphabet


class GeneratorFactory:
    """Abstract Factory – tworzy gotowe generatory dla typowych scenariuszy."""
    
    @staticmethod
    def default_bruteforce(min_len: int = 4, max_len: int = 7) -> PasswordGenerator:
        return (
            GeneratorBuilder()
            .with_default_alphabet()
            .with_length_range(min_len, max_len)
            .build()
        )

    @staticmethod
    def custom_alphabet(charset: str, min_len: int = 4, max_len: int = 7) -> PasswordGenerator:
        return (
            GeneratorBuilder()
            .with_alphabet(charset)
            .with_length_range(min_len, max_len)
            .build()
        )
    
    @staticmethod
    def file_dictionary(file_path: str, min_len: int = 4, max_len: int = 7) -> PasswordGenerator:
        from .strategies import FileDictionaryStrategy
        strategy = FileDictionaryStrategy(
            file_path=file_path,
            min_length=min_len,
            max_length=max_len
        )
        return PasswordGenerator(strategy)