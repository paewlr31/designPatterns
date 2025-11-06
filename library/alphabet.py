"""
alphabet.py
-----------
Definicje zestawów znaków (alfabetów) używanych przez generatory permutacji.
"""

import string

# gotowe, najczęściej używane alfabety
ASCII_LETTERS = string.ascii_letters
DIGITS = string.digits
ASCII_LETTERS_DIGITS = string.ascii_letters + string.digits
PRINTABLE = string.printable[:-5]   # bez białych znaków

# przykładowy własny alfabet
HEX_LOWER = "0123456789abcdef"
HEX_UPPER = "0123456789ABCDEF"