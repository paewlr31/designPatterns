# library/factory.py
from abc import ABC, abstractmethod
from .builder import PasswordGeneratorBuilder
from .strategies import BruteForceStrategy, DictionaryStrategy

class GeneratorFactory(ABC):
    @abstractmethod
    def create_builder(self) -> PasswordGeneratorBuilder:
        ...

class BruteForceFactory(GeneratorFactory):
    def create_builder(self) -> PasswordGeneratorBuilder:
        return (PasswordGeneratorBuilder()
                .with_bruteforce()
                .with_adaptive_chunks())

class DictionaryFactory(GeneratorFactory):
    def __init__(self, wordlist: list):
        self.wordlist = wordlist

    def create_builder(self) -> PasswordGeneratorBuilder:
        return (PasswordGeneratorBuilder()
                .with_dictionary(self.wordlist)
                .with_fixed_chunks(chunk_size=1000))