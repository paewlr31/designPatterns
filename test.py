# p2p_brute_final_sync.py
# DZIAŁA NA TELEFONIE (Pydroid3), LAPTOPIE, KOMPUTERZE
# 100% SYNCHRONIZACJA: JEDNO HASŁO, PACZKI ROZDZIELANE, RECLAIM, ELECTION

import hashlib
import json
import time
import threading
import socket
import uuid
import itertools
import random

# === KONFIGURACJA ===
BROADCAST_IP = '<broadcast>'
PORT = 5007
CHARSET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
PASSWORD_LEN = 4
CHUNK_SIZE = 1_000_000
NODE_ID = str(uuid.uuid4())[:8]
BROADCAST_INTERVAL = 0.6
IN_PROGRESS_TTL = 8.0  # reclaim po 8s

# === STAN ===
state = {
    "seed": None,
    "seed_creator": None,
    "target_hash": None,
    "found_password": None,
    "chunks": {},  # {cid: {"status": "todo"/"in_progress"/"done", "owner": node_id, "ts": float}}
    "total_chunks": 0
}

lock = threading.Lock()
dirty = False

# === PRZESTRZEŃ ===
TOTAL_PASSWORDS = len(CHARSET) ** PASSWORD_LEN
TOTAL_CHUNKS = (TOTAL_PASSWORDS + CHUNK_SIZE - 1) // CHUNK_SIZE

# === INICJALIZACJA CHUNKS ===
with lock:
    for i in range(TOTAL_CHUNKS):
        state["chunks"][i] = {"status": "todo", "owner": None, "ts": 0.0}
    state["total_chunks"] = TOTAL_CHUNKS

# === GENERATOR HASEŁ ===
def full_password_generator():
    for length in range(1, PASSWORD_LEN + 1):
        for combo in itertools.product(CHARSET, repeat=length):
            yield ''.join(combo)

def get_chunk_passwords(chunk_id):
    start_idx = chunk_id * CHUNK_SIZE
    end_idx = min(start_idx + CHUNK_SIZE, TOTAL_PASSWORDS)
    if start_idx >= TOTAL_PASSWORDS:
        return
    it = full_password_generator()
    for _ in range(start_idx):
        try: next(it)
        except StopIteration: return
    count = 0
    for pwd in it:
        if count >= (end_idx - start_idx): break
        yield pwd
        count += 1

def crack_chunk(chunk_id, target_hash):
    print(f"[{NODE_ID}] Łamię paczkę {chunk_id}")
    for pwd in get_chunk_passwords(chunk_id):
        if state["found_password"]:
            return None
        if hashlib.md5(pwd.encode()).hexdigest() == target_hash:
            return pwd
    return None

# === WYSYŁANIE ===
def send_state_loop():
    global dirty
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    while True:
        if dirty:
            with lock:
                msg = json.dumps({
                    "node_id": NODE_ID,
                    "seed": state["seed"],
                    "seed_creator": state["seed_creator"],
                    "target_hash": state["target_hash"],
                    "found_password": state["found_password"],
                    "chunks": state["chunks"],
                    "total_chunks": TOTAL_CHUNKS
                }).encode()
                dirty = False
            try:
                sock.sendto(msg, (BROADCAST_IP, PORT))
            except:
                pass
        time.sleep(BROADCAST_INTERVAL)

# === NASŁUCH ===
def listen_for_states():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', PORT))
    print(f"[{NODE_ID}] NASŁUCHUJĘ...")

    while True:
        try:
            data, addr = sock.recvfrom(65536)
            remote = json.loads(data.decode())
            if remote["node_id"] == NODE_ID:
                continue
            print(f"[{NODE_ID}] ODEBRANO OD {remote['node_id']} (IP: {addr[0]})")
            merge_state(remote)
        except:
            pass

# === SCALANIE + ELECTION + RECLAIM ===
known_creators = {}  # {creator_id: {"seed": int, "hash": str, "ts": float}}

def merge_state(remote):
    global dirty
    with lock:
        now = time.time()
        rid = remote["node_id"]

        # 1. ZNALEZIONO HASŁO → KONIEC
        if remote.get("found_password") and not state["found_password"]:
            state["found_password"] = remote["found_password"]
            print(f"\nHASŁO ZNALEZIONE PRZEZ {rid}: {state['found_password']}")
            dirty = True
            return

        # 2. ZBIERZ SEEDY
        if remote["seed"] is not None and remote["seed_creator"]:
            known_creators[remote["seed_creator"]] = {
                "seed": remote["seed"],
                "hash": remote["target_hash"],
                "ts": now
            }

        # 3. ELECTION: wybierz najniższy creator_id
        if known_creators:
            leader_id = min(known_creators.keys())
            leader = known_creators[leader_id]
            if state["seed_creator"] != leader_id:
                print(f"\nELECTION: przechodzę na seed od {leader_id}")
                state["seed"] = leader["seed"]
                state["seed_creator"] = leader_id
                state["target_hash"] = leader["hash"]
                dirty = True

        # 4. SCAL CHUNKI
        for cid_str, r_entry in remote.get("chunks", {}).items():
            try:
                cid = int(cid_str)
            except:
                continue
            if cid not in state["chunks"]:
                continue
            local = state["chunks"][cid]
            r_ts = r_entry.get("ts", 0)
            l_ts = local.get("ts", 0)

            if r_ts > l_ts:
                state["chunks"][cid] = r_entry.copy()
            elif r_ts == l_ts:
                if r_entry["status"] == "done" and local["status"] != "done":
                    state["chunks"][cid] = r_entry.copy()

        # 5. RECLAIM STARE IN_PROGRESS
        for cid, entry in list(state["chunks"].items()):
            if entry["status"] == "in_progress" and now - entry["ts"] > IN_PROGRESS_TTL:
                if entry["owner"] != NODE_ID:
                    print(f"RECLAIM: paczka {cid} wraca do todo (owner {entry['owner']} padł)")
                    state["chunks"][cid] = {"status": "todo", "owner": None, "ts": 0.0}
                    dirty = True

        dirty = True

# === REZERWACJA PACZKI ===
def reserve_chunk():
    now = time.time()
    with lock:
        for cid in range(TOTAL_CHUNKS):
            entry = state["chunks"].get(cid)
            if entry and entry["status"] == "todo":
                state["chunks"][cid] = {"status": "in_progress", "owner": NODE_ID, "ts": now}
                print(f"[{NODE_ID}] ZAREZERWOWANO paczkę {cid}")
                return cid
    return None

def mark_done(cid):
    with lock:
        state["chunks"][cid] = {"status": "done", "owner": NODE_ID, "ts": time.time()}
        global dirty
        dirty = True

# === MAIN ===
def main():
    print(f"\nP2P BRUTE FORCE [ID: {NODE_ID}]")

    # WĄTKI
    threading.Thread(target=listen_for_states, daemon=True).start()
    time.sleep(0.5)
    threading.Thread(target=send_state_loop, daemon=True).start()

    # CZEKAJ NA SEED
    start = time.time()
    while state["seed"] is None and time.time() - start < 5:
        time.sleep(0.3)

    # STWÓRZ, JEŚLI BRAK
    if state["seed"] is None:
        with lock:
            pwd = ''.join(random.choice(CHARSET) for _ in range(PASSWORD_LEN))
            state["seed"] = random.randint(1, 10**9)
            state["seed_creator"] = NODE_ID
            state["target_hash"] = hashlib.md5(pwd.encode()).hexdigest()
            known_creators[NODE_ID] = {"seed": state["seed"], "hash": state["target_hash"], "ts": time.time()}
            print(f"\nROZPOCZYNAM NOWĄ SIEĆ!")
            print(f"  hasło: {pwd}")

    time.sleep(1.5)

    print(f"\nŁamię hash: {state['target_hash'][:16]}... | {TOTAL_CHUNKS} paczek")

    # GŁÓWNA PĘTLA
    while not state["found_password"]:
        cid = reserve_chunk()
        if cid is None:
            time.sleep(1)
            continue

        result = crack_chunk(cid, state["target_hash"])
        if result:
            with lock:
                state["found_password"] = result
                print(f"\nJA ZNALAZŁEM: {result}")
                mark_done(cid)
            break
        else:
            mark_done(cid)
            print(f"[{NODE_ID}] paczka {cid} zakończona")

    print(f"\nHASŁO: {state['found_password']}")
    print("KONIEC.")
    time.sleep(2)

if __name__ == "__main__":
    main()