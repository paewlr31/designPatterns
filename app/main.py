"""
main.py
-------
Aplikacja demonstracyjna – prosty, rozproszony brute-force SHA-1
wykorzystujący bibliotekę `library`.
"""

import hashlib
import time
import socket
import threading
from typing import Optional

# ---------- importy z biblioteki ----------
from library.factory import GeneratorFactory
from library.alphabet import ASCII_LETTERS_DIGITS

# ---------- konfiguracja ----------
TARGET_HASH = hashlib.sha1(b"QT98iE9").hexdigest()
PASSWORD_LENGTH = 4
MULTICAST_GROUP = "224.0.0.251"
MULTICAST_PORT = 50001
TASK_PORT = 50002
PING_INTERVAL = 3
SYNC_INTERVAL = 8
TASK_TIMEOUT = 30
SYNC_WAIT_TIMEOUT = 12


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class DemoNode:
    def __init__(self):
        self.ip = get_local_ip()
        self.generator = GeneratorFactory.brute_force(
            charset=ASCII_LETTERS_DIGITS,
            length=PASSWORD_LENGTH,
            chunk_size=1_000_000,
        )
        self.total_batches = (len(ASCII_LETTERS_DIGITS) ** PASSWORD_LENGTH) // 1_000_000 + 1

        self.peers: dict[str, float] = {}
        self.done_batches: set[int] = set()
        self.assigned: dict[str, tuple[int, float]] = {}
        self.found: Optional[str] = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()

        print(f"[START] Node {self.ip}")

        # sockets
        self.mcast_sock = self._create_mcast_socket()
        self.task_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.task_sock.bind(("", TASK_PORT))

        # wątki
        threading.Thread(target=self._mcast_listener, daemon=True).start()
        threading.Thread(target=self._task_listener, daemon=True).start()
        threading.Thread(target=self._ping_sender, daemon=True).start()
        threading.Thread(target=self._sync_sender, daemon=True).start()
        threading.Thread(target=self._cleanup, daemon=True).start()

        self._wait_for_network()
        threading.Thread(target=self._worker_loop, daemon=True).start()

    # ------------------------------------------------------------------
    #  Sieć
    # ------------------------------------------------------------------
    def _create_mcast_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", MULTICAST_PORT))
        mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        return sock

    def _mcast_listener(self):
        while not self.stop_event.is_set():
            try:
                data, (addr, _) = self.mcast_sock.recvfrom(1024)
                msg = data.decode()
                if addr == self.ip:
                    continue

                with self.lock:
                    self.peers[addr] = time.time()

                if msg.startswith("PING:"):
                    pass
                elif msg.startswith("SYNC:"):
                    batches = {int(x) for x in msg.split(":", 1)[1].split(",") if x}
                    old = len(self.done_batches)
                    self.done_batches.update(batches)
                    if len(self.done_batches) > old:
                        print(f"[SYNC] Otrzymano {len(batches)} paczek od {addr}")
            except Exception:
                continue

    def _ping_sender(self):
        msg = f"PING:{self.ip}".encode()
        while not self.stop_event.is_set():
            try:
                self.mcast_sock.sendto(msg, (MULTICAST_GROUP, MULTICAST_PORT))
            except Exception:
                pass
            time.sleep(PING_INTERVAL)

    def _sync_sender(self):
        while not self.stop_event.is_set():
            time.sleep(SYNC_INTERVAL)
            self._broadcast_sync()

    def _broadcast_sync(self):
        with self.lock:
            csv = ",".join(map(str, sorted(self.done_batches)))
        msg = f"SYNC:{csv}".encode()
        try:
            self.mcast_sock.sendto(msg, (MULTICAST_GROUP, MULTICAST_PORT))
        except Exception:
            pass

    def _send_to_peers(self, txt: str):
        msg = txt.encode()
        for ip in list(self.peers.keys()):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.5)
                s.sendto(msg, (ip, TASK_PORT))
                s.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    #  Task listener
    # ------------------------------------------------------------------
    def _task_listener(self):
        while not self.stop_event.is_set():
            try:
                data, (addr, _) = self.task_sock.recvfrom(4096)
                msg = data.decode()
                if addr == self.ip:
                    continue

                with self.lock:
                    self.peers[addr] = time.time()

                if msg.startswith("TASK_START:"):
                    batch = int(msg.split(":", 1)[1])
                    self.assigned[addr] = (batch, time.time())
                    print(f"[INFO] {addr} → paczka {batch}")

                elif msg.startswith("TASK_DONE:"):
                    batch = int(msg.split(":", 1)[1])
                    self.done_batches.add(batch)
                    self.assigned.pop(addr, None)
                    print(f"[DONE] {addr} zakończył {batch}")
                    self._broadcast_sync()

                elif msg.startswith("FOUND:"):
                    pwd = msg.split(":", 1)[1]
                    print(f"\n[FOUND] Hasło: {pwd} (przez {addr})")
                    self.found = pwd
                    self.stop_event.set()
                    self._send_to_peers(f"FOUND:{pwd}")

                elif msg.startswith("SYNC_REQ:"):
                    self._broadcast_sync()
            except Exception:
                continue

    # ------------------------------------------------------------------
    #  Praca
    # ------------------------------------------------------------------
    def _next_batch(self) -> int:
        with self.lock:
            batch = 0
            while (
                batch in self.done_batches
                or any(v[0] == batch for v in self.assigned.values())
            ):
                batch += 1
            self.assigned[self.ip] = (batch, time.time())
            return batch

    def _worker_loop(self):
        while not self.stop_event.is_set():
            batch = self._next_batch()
            print(f"[TASK] Biorę paczkę {batch}")
            self._send_to_peers(f"TASK_START:{batch}")

            # pobieramy fragment z generatora
            start_idx = batch * 1_000_000
            chunk_iter = self.generator.strategy.candidates(start_idx, 1_000_000)

            found = self._check_chunk(chunk_iter)
            if found:
                self.found = found
                self.stop_event.set()
                self._send_to_peers(f"FOUND:{found}")
                print(f"[FOUND] Znalazłem: {found}")
                break

            with self.lock:
                self.done_batches.add(batch)
                self.assigned.pop(self.ip, None)
            self._send_to_peers(f"TASK_DONE:{batch}")
            self._broadcast_sync()

    def _check_chunk(self, it):
        for pwd in it:
            if self.stop_event.is_set():
                return None
            if hashlib.sha1(pwd.encode()).hexdigest() == TARGET_HASH:
                return pwd
        return None

    # ------------------------------------------------------------------
    #  Czekanie na sieć
    # ------------------------------------------------------------------
    def _wait_for_network(self):
        print("[SYNC] Czekam na sieć (max 12s)…")
        self._send_sync_request()
        if not any(threading.Event().wait(SYNC_WAIT_TIMEOUT) for _ in range(1)):
            print("[SYNC] Timeout – startuję lokalnie.")
        else:
            print(f"[SYNC] Połączono! Znam {len(self.done_batches)} paczek.")

    def _send_sync_request(self):
        msg = b"SYNC_REQ:"
        for ip in list(self.peers):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.sendto(msg, (ip, TASK_PORT))
                s.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    #  Czyszczenie nieaktywnych peerów
    # ------------------------------------------------------------------
    def _cleanup(self):
        while not self.stop_event.is_set():
            time.sleep(5)
            now = time.time()
            with self.lock:
                dead = [ip for ip, t in self.peers.items() if now - t > TASK_TIMEOUT]
                for ip in dead:
                    self.peers.pop(ip, None)
                    self.assigned.pop(ip, None)
                    print(f"[OFFLINE] {ip}")

    # ------------------------------------------------------------------
    #  Uruchomienie
    # ------------------------------------------------------------------
    def run(self):
        try:
            while not self.stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[STOP]")
            self.stop_event.set()


if __name__ == "__main__":
    node = DemoNode()
    node.run()