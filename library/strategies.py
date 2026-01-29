from __future__ import annotations
import itertools
from typing import Iterator, Protocol, Any
from .alphabet import Alphabet
from .generator import CoreBruteGenerator


class GenerationStrategy(Protocol):
    """Protokół strategii generowania haseł."""

    def generate(self, start_idx: int, count: int) -> Iterator[str]:
        """Generuje count haseł zaczynając od globalnego indeksu start_idx."""
        ...

    def total_combinations(self, min_len: int, max_len: int) -> int:
        """Zwraca całkowitą liczbę kombinacji dla podanych długości."""
        ...


class BruteForceStrategy:
    """
    Adapter-strategia, która deleguje pracę do CoreBruteGenerator.
    Zostało tak napisane, żeby kod, który importuje 'BruteForceStrategy'
    dalej działał — ale ciężka praca wykonuje się w CoreBruteGenerator.
    """

    def __init__(self, alphabet: Alphabet, min_length: int, max_length: int):
        self._core = CoreBruteGenerator(alphabet, min_length, max_length)

    def total_combinations(self, min_len: int = None, max_len: int = None) -> int:
        return self._core.total_combinations(min_len, max_len)

    def generate(self, start_idx: int, count: int) -> Iterator[str]:
        return self._core.generate(start_idx, count)



class FileDictionaryStrategy:
    """
    Strategia Słownikowa (File-based):
    Czyta hasła z pliku tekstowego "w locie".
    Nie ładuje całego pliku do pamięci RAM.
    """

    def __init__(self, file_path: str, alphabet: Any = None, min_length: int = 0, max_length: int = 0):
        self.file_path = file_path
        # Parametry długości są ważne - jeśli słownik ma hasło "a", 
        # a my szukamy min_length=5, to generator powinien je pominąć.
        self.min_length = min_length
        self.max_length = max_length

    def _get_generator(self) -> Iterator[str]:
        """
        Prywatna metoda pomocnicza.
        Otwiera plik i zwraca generator, który wypluwa po jednym słowie na raz.
        Dzięki 'yield' Python pamięta wskaźnik pliku i nie czyta wszystkiego naraz.
        """
        try:
            # encoding='utf-8' jest standardem, errors='ignore' zapobiegnie wywaleniu programu
            # jeśli w pliku trafi się jakiś dziwny, uszkodzony znak.
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # split() domyślnie dzieli po białych znakach (spacja, tab, enter).
                    # To idealnie pasuje do Twojego pliku oddzielonego spacjami.
                    for word in line.split():
                        # Filtrujemy w locie. Jeśli hasło nie pasuje do długości,
                        # w ogóle nie opuszcza tego generatora.
                        if self.min_length <= len(word) <= self.max_length:
                            yield word
        except FileNotFoundError:
            # Pusty generator w razie błędu pliku
            return

    def total_combinations(self, min_len: int = None, max_len: int = None) -> int:
        """
        Niestety, aby policzyć elementy w strumieniu, musimy go "przejść".
        To może chwilę potrwać przy 10mln haseł, ale nie zużyje pamięci.
        """
        lines = sum(1 for _ in self._get_generator())
        return lines

    def generate(self, start_idx: int, count: int) -> Iterator[str]:
        """
        Tu dzieje się magia optymalizacji.
        Używamy itertools.islice, aby przesunąć wirtualny wskaźnik
        do start_idx, a potem pobrać tylko 'count' elementów.
        """
        generator = self._get_generator()
        
        # islice(iterable, start, stop)
        # To działa jak wycinanie listy [start:start+count], ale na strumieniu danych.
        # Python pominie pierwsze 'start_idx' elementów (czytając je i odrzucając),
        # a potem zwróci tylko tyle ile chcesz.
        passwords = itertools.islice(generator, start_idx, start_idx + count)

        # print("______________________________________")
        # print(list(itertools.islice(generator, start_idx, start_idx + 10)))
        # # if passwords are empty, stop the program

        return passwords