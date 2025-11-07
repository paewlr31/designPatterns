import string
from typing import Iterable, List


class Alphabet:
    """Reprezentuje zestaw znaków do generowania haseł."""
    
    DEFAULT = string.ascii_letters + string.digits  # a-zA-Z0-9

    def __init__(self, charset: str = None):
        self.charset = charset or self.DEFAULT
        if not self.charset:
            raise ValueError("Alfabet nie może być pusty")
        self.base = len(self.charset)

    def __getitem__(self, index: int) -> str:
        return self.charset[index % self.base]

    def __len__(self) -> int:
        return self.base

    def __iter__(self) -> Iterable[str]:
        return iter(self.charset)

    def __repr__(self) -> str:
        return f"Alphabet('{self.charset[:10]}{'...' if len(self.charset) > 10 else ''}', base={self.base})"