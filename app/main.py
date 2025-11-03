# app/main.py
import time
import random
import string
import threading
from library.factory import BruteForceFactory
from library.builder import PasswordGeneratorBuilder
from library.p2p import P2PNode

CHUNK_SIZE = 1_000_000

def generate_random_password(length: int = 4) -> str:
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

def worker(node: P2PNode, target: str, builder: PasswordGeneratorBuilder, total_space: int, chunk_id: int):
    start_idx = chunk_id * CHUNK_SIZE
    end_idx = min(start_idx + CHUNK_SIZE, total_space)
    print(f"[PACZKA {chunk_id+1}] Start: {start_idx} → {end_idx-1}")

    iterator = builder.build_iterator(start=start_idx, end=end_idx)
    attempts = 0
    start_time = time.time()

    for candidate in iterator:
        attempts += 1
        if candidate == target:
            elapsed = time.time() - start_time
            print(f"\nHASŁO ZNALEZIONE w paczce {chunk_id+1}: '{candidate}' ({attempts:,} prób, {elapsed:.2f}s)")
            node.report_done(chunk_id, found=True, password=candidate)
            return

        if node.password_found:
            break

        if attempts % 200_000 == 0:
            time.sleep(0.001)  # oddech

    elapsed = time.time() - start_time
    print(f"[PACZKA {chunk_id+1}] zakończona – nie znaleziono ({attempts:,} prób, {elapsed:.2f}s)")
    node.report_done(chunk_id, found=False, password=None)

def main():
    TARGET = generate_random_password(4)
    print(f"\n[START] Szukane hasło: {TARGET}\n")

    factory = BruteForceFactory()
    builder: PasswordGeneratorBuilder = factory.create_builder()
    total_space = builder.build_full_space_size()
    num_chunks = (total_space + CHUNK_SIZE - 1) // CHUNK_SIZE
    print(f"[INFO] Przestrzeń: {total_space:,} | Paczek: {num_chunks}")

    node = P2PNode()
    node.start()

    # Inicjalizacja – pierwszy node tworzy paczki
    node.initialize_chunks(num_chunks)

    try:
        while not node.password_found:
            chunk_id = node.take_next_chunk()
            if chunk_id is None:
                time.sleep(1)
                continue

            threading.Thread(
                target=worker,
                args=(node, TARGET, builder, total_space, chunk_id),
                daemon=True
            ).start()

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[ZAKOŃCZENIE] Ctrl+C")
    finally:
        node.goodbye()

if __name__ == "__main__":
    main()