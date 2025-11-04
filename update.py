import socket
import threading
import time
import ipaddress
import hashlib
import itertools
import string
import sys

BROADCAST_PORT = 50001
TASK_PORT = 50002
DISCOVERY_INTERVAL = 3
TASK_BATCH_SIZE = 10000000  # ile kombinacji w paczce
CHARSET = string.ascii_letters + string.digits  # a-zA-Z0-9
PASSWORD_LENGTH = 6

TARGET_HASH = hashlib.sha1(b"QwErT9").hexdigest()  # <- przykładowy cel


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def get_broadcast_address(ip):
    try:
        net = ipaddress.ip_network(ip + "/24", strict=False)
        return str(net.broadcast_address)
    except Exception:
        return "255.255.255.255"


class DistributedBruteForcer:
    def __init__(self):
        self.ip = get_local_ip()
        self.broadcast_ip = get_broadcast_address(self.ip)
        self.peers = set()
        self.done_batches = set()
        self.current_batch = None
        self.assigned_batches = {}  # peer_ip -> batch_id (co aktualnie robi dany peer)
        self.global_stop = False
        self.lock = threading.Lock()

        print(f"[START] Node {self.ip} (broadcast {self.broadcast_ip})")

        threading.Thread(target=self._discover_peers, daemon=True).start()
        threading.Thread(target=self._listen_discovery, daemon=True).start()
        threading.Thread(target=self._listen_messages, daemon=True).start()
        threading.Thread(target=self._work_loop, daemon=True).start()

    # ======== DISCOVERY ========
    def _discover_peers(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        msg = f"HELLO:{self.ip}:{TASK_PORT}".encode()
        while not self.global_stop:
            sock.sendto(msg, (self.broadcast_ip, BROADCAST_PORT))
            time.sleep(DISCOVERY_INTERVAL)

    def _listen_discovery(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("", BROADCAST_PORT))
        while not self.global_stop:
            data, addr = sock.recvfrom(1024)
            text = data.decode()
            if text.startswith("HELLO:"):
                _, ip, port = text.split(":")
                if ip != self.ip:
                    peer = (ip, int(port))
                    with self.lock:
                        was_new = peer not in self.peers
                        self.peers.add(peer)
                    if was_new:
                        print(f"[DISCOVER] znaleziono node: {ip}")
                        self._log_status()

    # ======== COMMUNICATION ========
    def _listen_messages(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("", TASK_PORT))
        while not self.global_stop:
            data, addr = sock.recvfrom(4096)
            msg = data.decode()
            peer_ip = addr[0]

            if msg.startswith("TASK_START:"):
                _, batch = msg.split(":")
                batch = int(batch)
                with self.lock:
                    self.assigned_batches[peer_ip] = batch
                print(f"[INFO] node {peer_ip} robi paczkę teraz: {batch}")
                self._log_status()

            elif msg.startswith("TASK_DONE:"):
                _, batch = msg.split(":")
                batch = int(batch)
                with self.lock:
                    self.done_batches.add(batch)
                    if peer_ip in self.assigned_batches:
                        del self.assigned_batches[peer_ip]
                print(f"[DONE] node {peer_ip} zakończył paczkę: {batch}")
                self._log_status()

            elif msg.startswith("FOUND:"):
                _, password = msg.split(":", 1)
                print(f"\n[FOUND] Hasło znalezione: {password} (przez {peer_ip})")
                self.global_stop = True

            elif msg.startswith("SYNC:"):
                _, csv = msg.split(":", 1)
                done = {int(x) for x in csv.split(",") if x}
                with self.lock:
                    old_count = len(self.done_batches)
                    self.done_batches |= done
                if len(self.done_batches) > old_count:
                    self._log_status()

    def _send_to_all(self, message):
        for peer in list(self.peers):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(message.encode(), peer)
                sock.close()
            except Exception:
                pass

    # ======== TASK LOGIC ========
    def _next_batch(self):
        """Zwraca indeks kolejnej nieukończonej paczki."""
        with self.lock:
            b = 0
            while b in self.done_batches or any(b == v for v in self.assigned_batches.values()):
                b += 1
            self.current_batch = b
            return b

    def _work_loop(self):
        while not self.global_stop:
            batch_id = self._next_batch()
            print(f"[TASK] to ja biorę: {batch_id}")
            self._send_to_all(f"TASK_START:{batch_id}")

            start = batch_id * TASK_BATCH_SIZE
            print(f"[TASK] Paczka {batch_id} od {start}")
            found = self._process_batch(batch_id, start)

            if found:
                self.global_stop = True
                msg = f"FOUND:{found}"
                self._send_to_all(msg)
                print(f"\n[FOUND] Hasło znalezione lokalnie: {found}")
                break
            else:
                with self.lock:
                    self.done_batches.add(batch_id)
                    if self.ip in [p[0] for p in self.peers]:
                        pass  # nie usuwamy siebie
                self._send_to_all(f"TASK_DONE:{batch_id}")
                self._log_status()

    def _process_batch(self, batch_id, start_index):
        """Przetwarza zakres kombinacji."""
        total = len(CHARSET) ** PASSWORD_LENGTH
        for i in range(TASK_BATCH_SIZE):
            if self.global_stop:
                return None
            idx = start_index + i
            if idx >= total:
                return None
            pwd = self._index_to_password(idx)
            h = hashlib.sha1(pwd.encode()).hexdigest()
            if h == TARGET_HASH:
                return pwd
        return None

    def _index_to_password(self, idx):
        """Konwertuje numer kombinacji na hasło."""
        base = len(CHARSET)
        chars = []
        for _ in range(PASSWORD_LENGTH):
            chars.append(CHARSET[idx % base])
            idx //= base
        return "".join(reversed(chars))

    def _log_status(self):
        """Wypisuje aktualny stan: zrobione, aktualnie robione, dostępne peer'y."""
        with self.lock:
            done_str = ", ".join(map(str, sorted(self.done_batches))) if self.done_batches else "brak"
            working = []
            for peer_ip, batch in self.assigned_batches.items():
                if peer_ip == self.ip:
                    working.append(f"{batch} (ja)")
                else:
                    working.append(f"{batch} ({peer_ip})")
            working_str = ", ".join(working) if working else "brak"

            peer_ips = sorted([p[0] for p in self.peers if p[0] != self.ip])
            peers_str = ", ".join(peer_ips) if peer_ips else "brak"

        print(f"[STATUS] zrobione paczki: {done_str}")
        print(f"[STATUS] robione aktualnie: {working_str}")
        if peers_str != "brak":
            print(f"[STATUS] inne nody: {peers_str}")


if __name__ == "__main__":
    node = DistributedBruteForcer()
    try:
        while not node.global_stop:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP]")