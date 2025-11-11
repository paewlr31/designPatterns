#!/usr/bin/env python3
import socket
import threading
import time
import hashlib
import argparse
import re
import sys
from pathlib import Path

# Dodajemy bibliotekę do ścieżki
sys.path.append(str(Path(__file__).parent.parent))

from library.factory import GeneratorFactory
from library.generator import PermutationIterator

from dotenv import load_dotenv
import os

# === KONFIGURACJA Z .env ===
load_dotenv()

KNOWN_PEERS = os.getenv("KNOWN_PEERS", "")
KNOWN_PEERS = [ip.strip() for ip in KNOWN_PEERS.split(",") if ip.strip()]

BROADCAST_PORT = 50001
TASK_PORT = 50002
PING_INTERVAL = 3
SYNC_INTERVAL = 8
TASK_BATCH_SIZE = 1000000
TASK_TIMEOUT = 30
SYNC_WAIT_TIMEOUT = 12


# === POMOCNICZE ===
def get_hamachi_ip():
    """Pobiera IP Hamachi (25.x.x.x)"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Łączymy się z zewnętrznym IP aby uzyskać lokalny IP
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        # Sprawdź czy to IP Hamachi
        if local_ip.startswith("25."):
            return local_ip
        # Jeśli nie, spróbuj znaleźć interfejs Hamachi
        import socket as sock
        hostname = sock.gethostname()
        for ip in sock.gethostbyname_ex(hostname)[2]:
            if ip.startswith("25."):
                return ip
        return local_ip
    except:
        return "127.0.0.1"
    finally:
        s.close()


def valid_password(pwd: str):
    if not (4 <= len(pwd) <= 7):
        return False, "Hasło musi mieć długość między 4 a 7 znaków."
    if not re.fullmatch(r"[A-Za-z0-9]+", pwd):
        return False, "Hasło zawiera niedozwolone znaki — dozwolone: a-zA-Z0-9."
    return True, ""


class DistributedBruteForcer:
    def __init__(self, provided_password=None):
        self.ip = get_hamachi_ip()
        self.peers = {}
        self.done_batches = set()
        self.assigned_batches = {}
        self.global_stop = False
        self.lock = threading.Lock()
        self.sync_ready = threading.Event()

        self.target_hash = None
        self.hash_ready = threading.Event()

        self.proposed_password = None
        self.proposed_hash = None
        if provided_password:
            ok, msg = valid_password(provided_password)
            if not ok:
                print(f"[BŁĄD] {msg}")
                sys.exit(1)
            self.proposed_password = provided_password
            self.proposed_hash = hashlib.sha1(provided_password.encode()).hexdigest()

        print(f"[START] Node {self.ip} (Hamachi)")

        # Dodaj znane peery
        for peer in KNOWN_PEERS:
            if peer != self.ip:
                self.peers[peer] = 0

        # === SIEĆ ===
        self.bcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.bcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.bcast_sock.bind(("", BROADCAST_PORT))
        except Exception as e:
            print(f"[FATAL] Bind broadcast: {e}")
            sys.exit(1)

        self.task_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.task_sock.bind(("", TASK_PORT))
        except Exception as e:
            print(f"[FATAL] Bind task: {e}")
            sys.exit(1)

        # === BIBLIOTEKA ===
        self.generator = GeneratorFactory.default_bruteforce(min_len=4, max_len=7)
        self.strategy = self.generator.strategy

        # === WĄTKI ===
        threading.Thread(target=self._broadcast_listener, daemon=True).start()
        threading.Thread(target=self._task_listener, daemon=True).start()
        threading.Thread(target=self._send_ping, daemon=True).start()
        threading.Thread(target=self._send_sync_periodic, daemon=True).start()
        threading.Thread(target=self._cleanup, daemon=True).start()
        threading.Thread(target=self._work_loop, daemon=True).start()

        self._wait_for_network()

    def _wait_for_network(self):
        print(f"[SYNC] Czekam na hash (max {SYNC_WAIT_TIMEOUT}s)...")
        self._send_sync_request()
        got = self.hash_ready.wait(SYNC_WAIT_TIMEOUT)

        if got:
            if self.proposed_password:
                print("[INFO] Znaleziono sieć — anuluję lokalne hasło.")
                self.proposed_password = None
            self.sync_ready.set()
            self._log_status()
            return

        with self.lock:
            peers = len(self.peers)

        if self.proposed_password:
            self.target_hash = self.proposed_hash
            self.hash_ready.set()
            print("[SYNC] Tworzę sieć z podanym hasłem.")
            self._broadcast_hash_set(self.target_hash)
            self.sync_ready.set()
            self._log_status()
            return

        if peers == 0:
            pwd = self._ask_password()
        else:
            print(f"[SYNC] Czekam jeszcze {SYNC_WAIT_TIMEOUT}s...")
            got = self.hash_ready.wait(SYNC_WAIT_TIMEOUT)
            if got:
                self.sync_ready.set()
                self._log_status()
                return
            pwd = self._ask_password()

        self.proposed_password = pwd
        self.proposed_hash = hashlib.sha1(pwd.encode()).hexdigest()
        self.target_hash = self.proposed_hash
        self.hash_ready.set()
        self._broadcast_hash_set(self.target_hash)
        self.sync_ready.set()
        self._log_status()

    def _ask_password(self):
        print("[SYNC] Podaj hasło do ustawienia (4-7 znaków, a-zA-Z0-9):")
        while True:
            try:
                pwd = input("> ").strip()
            except EOFError:
                print("\n[STOP]")
                self.global_stop = True
                sys.exit(0)
            ok, msg = valid_password(pwd)
            if ok:
                return pwd
            print(f"[BŁĄD] {msg}")

    def _broadcast_listener(self):
        while not self.global_stop:
            try:
                data, addr = self.bcast_sock.recvfrom(4096)
                msg, ip = data.decode(), addr[0]
                if ip == self.ip:
                    continue

                with self.lock:
                    if ip not in self.peers:
                        print(f"[DISCOVER] {ip}")
                    self.peers[ip] = time.time()

                if msg.startswith("PING:"):
                    pass
                elif msg.startswith("SYNC:"):
                    done = {int(x) for x in msg.split(":", 1)[1].split(",") if x}
                    with self.lock:
                        old = len(self.done_batches)
                        self.done_batches |= done
                    if len(self.done_batches) > old:
                        print(f"[SYNC] +{len(done)} paczek od {ip}")
                        self._log_status()
                    self.sync_ready.set()
                elif msg.startswith("HASH_SET:"):
                    h = msg.split(":", 1)[1].strip()
                    if self.target_hash != h:
                        print(f"[HASH] Nowy hash od {ip}")
                    self.target_hash = h
                    self.hash_ready.set()
                    self.sync_ready.set()
            except:
                continue

    def _send_ping(self):
        """Wysyła PING do wszystkich znanych peerów"""
        msg = f"PING:{self.ip}".encode()
        while not self.global_stop:
            self._broadcast_to_peers(msg, BROADCAST_PORT)
            time.sleep(PING_INTERVAL)

    def _send_sync_periodic(self):
        while not self.global_stop:
            time.sleep(SYNC_INTERVAL)
            self._broadcast_sync()
            if self.target_hash:
                self._broadcast_hash_set(self.target_hash)

    def _broadcast_sync(self):
        with self.lock:
            csv = ",".join(map(str, sorted(self.done_batches)))
        msg = f"SYNC:{csv}".encode()
        self._broadcast_to_peers(msg, BROADCAST_PORT)

    def _broadcast_hash_set(self, h):
        msg = f"HASH_SET:{h}".encode()
        self._broadcast_to_peers(msg, BROADCAST_PORT)
        print("[HASH] Rozgłoszono hash.")

    def _broadcast_to_peers(self, msg, port):
        """Wysyła wiadomość do wszystkich znanych peerów"""
        with self.lock:
            peer_list = list(self.peers.keys())
        
        for ip in peer_list:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.2)
                s.sendto(msg, (ip, port))
                s.close()
            except:
                pass

    def _send_sync_request(self):
        """Prosi wszystkie peery o synchronizację"""
        msg = b"SYNC_REQ:"
        for ip in list(self.peers):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.5)
                s.sendto(msg, (ip, TASK_PORT))
                s.close()
            except:
                pass

    def _task_listener(self):
        while not self.global_stop:
            try:
                data, addr = self.task_sock.recvfrom(4096)
                msg, ip = data.decode(), addr[0]
                if ip == self.ip:
                    continue

                with self.lock:
                    if ip not in self.peers:
                        print(f"[DISCOVER] node z TASK: {ip}")
                    self.peers[ip] = time.time()

                if msg.startswith("TASK_START:"):
                    b = int(msg.split(":", 1)[1])
                    with self.lock:
                        self.assigned_batches[ip] = (b, time.time())
                    print(f"[INFO] {ip} → {b}")
                    self._log_status()
                elif msg.startswith("TASK_DONE:"):
                    b = int(msg.split(":", 1)[1])
                    with self.lock:
                        self.done_batches.add(b)
                        self.assigned_batches.pop(ip, None)
                    print(f"[DONE] {ip} zakończył {b}")
                    self._broadcast_sync()
                    self._log_status()
                elif msg.startswith("FOUND:"):
                    pwd = msg.split(":", 1)[1]
                    print(f"\n[FOUND] Hasło: {pwd} (przez {ip})")
                    self.global_stop = True
                elif msg.startswith("SYNC_REQ:"):
                    self._broadcast_sync()
            except:
                continue

    def _send_to_all(self, msg):
        """Wysyła wiadomość do wszystkich peerów"""
        for ip in list(self.peers):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.5)
                s.sendto(msg.encode(), (ip, TASK_PORT))
                s.close()
            except:
                pass

    def _next_batch(self):
        with self.lock:
            b = 0
            while b in self.done_batches or any(v[0] == b for v in self.assigned_batches.values()):
                b += 1
            self.assigned_batches[self.ip] = (b, time.time())
            return b

    def _work_loop(self):
        print("[WORK] Czekam na hash...")
        while not self.global_stop and not self.hash_ready.is_set():
            time.sleep(0.5)
        if self.global_stop:
            return
        print("[WORK] Start!")

        while not self.global_stop:
            if not self.target_hash:
                self.hash_ready.clear()
                while not self.hash_ready.is_set() and not self.global_stop:
                    time.sleep(0.5)
                continue

            batch = self._next_batch()
            print(f"[TASK] Paczka {batch}")
            self._send_to_all(f"TASK_START:{batch}")

            start_idx = batch * TASK_BATCH_SIZE
            found = self._process_batch(start_idx)

            if found:
                self.global_stop = True
                self._send_to_all(f"FOUND:{found}")
                print(f"[FOUND] Znalazłem: {found}")
                break
            else:
                with self.lock:
                    self.done_batches.add(batch)
                    self.assigned_batches.pop(self.ip, None)
                self._send_to_all(f"TASK_DONE:{batch}")
                self._broadcast_sync()
                self._log_status()

    def _process_batch(self, start_idx):
        batch_gen = self.strategy.generate(start_idx, TASK_BATCH_SIZE)
        for pwd in batch_gen:
            if self.global_stop:
                return None
            if hashlib.sha1(pwd.encode()).hexdigest() == self.target_hash:
                return pwd
        return None

    def _cleanup(self):
        while not self.global_stop:
            time.sleep(5)
            now = time.time()
            with self.lock:
                dead = [ip for ip, t in self.peers.items() if t > 0 and now - t > TASK_TIMEOUT]
                for ip in dead:
                    del self.peers[ip]
                    self.assigned_batches.pop(ip, None)
                    print(f"[OFFLINE] {ip}")
            if dead:
                self._log_status()

    def _log_status(self):
        with self.lock:
            done = ", ".join(map(str, sorted(self.done_batches))) or "brak"
            working = [f"{b} ({'ja' if ip==self.ip else ip})" for ip, (b,_) in self.assigned_batches.items()]
            work_str = ", ".join(working) or "brak"
            peers_str = ", ".join(sorted(p for p in self.peers if p != self.ip)) or "brak"
            th = self.target_hash or "brak"
        print(f"[STATUS] zrobione: {done}")
        print(f"[STATUS] robione: {work_str}")
        print(f"[STATUS] nody: {peers_str}")
        print(f"[STATUS] hash: {th}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--password", "-p", help="Hasło do ustawienia")
    args = parser.parse_args()

    node = DistributedBruteForcer(args.password)
    try:
        while not node.global_stop:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP]")
        node.global_stop = True