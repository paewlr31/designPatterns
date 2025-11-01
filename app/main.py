# app/main.py
import time
import random
import string
from library.factory import BruteForceFactory
from library.builder import PasswordGeneratorBuilder

CHUNK_SIZE = 1_000_000  # 1 milion haseł na paczkę

def generate_random_password(length: int = 4) -> str:
    """Generuje losowe hasło z alfabetu (a-z, A-Z, 0-9)"""
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

def crack_password_in_chunks(target_password: str):
    factory = BruteForceFactory()
    builder = factory.create_builder()
    total_space = builder.build_full_space_size()
    print(f"[INFO] Przestrzeń haseł: 62^4 = {total_space:,} możliwości")
    print(f"[INFO] Szukam hasła: {target_password}")

    # Oblicz liczbę paczek
    num_chunks = (total_space + CHUNK_SIZE - 1) // CHUNK_SIZE
    print(f"[INFO] Podział na {num_chunks} paczek po {CHUNK_SIZE:,} haseł\n")

    start_idx = 0
    for chunk_id in range(num_chunks):
        end_idx = min(start_idx + CHUNK_SIZE, total_space)
        print(f"[PACZKA {chunk_id+1}/{num_chunks}] Pobieram paczkę... (indeksy: {start_idx} → {end_idx-1})")

        iterator = builder.build_iterator(start=start_idx, end=end_idx)
        attempts = 0
        chunk_start_time = time.time()

        for candidate in iterator:
            attempts += 1
            if candidate == target_password:
                elapsed = time.time() - chunk_start_time
                total_elapsed = time.time() - global_start_time
                print(f"\nHASŁO ZNALEZIONE! '{candidate}'")
                print(f"    → w paczce {chunk_id+1}, po {attempts} próbach w tej paczce")
                print(f"    → łączny czas: {total_elapsed:.2f}s")
                return

        elapsed = time.time() - chunk_start_time
        print(f"[PACZKA {chunk_id+1}] Rozkodowana... nie znaleziono hasła "
              f"({attempts:,} prób, {elapsed:.2f}s)")

        start_idx = end_idx

    print("\nPrzeszukano całą przestrzeń – hasło nie istnieje lub błąd.")

if __name__ == "__main__":
    global_start_time = time.time()
    TARGET = generate_random_password(4)
    print(f"[START] Generuję losowe hasło: {TARGET}\n")
    crack_password_in_chunks(TARGET)