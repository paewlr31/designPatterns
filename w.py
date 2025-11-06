import socket
import threading
import time
import hashlib
import string
import sys

# === USTAWIENIA ===
MULTICAST_GROUP = "224.0.0.251"
MULTICAST_PORT = 50001
TASK_PORT = 50002
PING_INTERVAL = 3
SYNC_INTERVAL = 8
TASK_BATCH_SIZE = 1000000
CHARSET = string.ascii_letters + string.digits
MIN_PASSWORD_LENGTH = 4
MAX_PASSWORD_LENGTH = 7
TASK_TIMEOUT = 30
SYNC_WAIT_TIMEOUT = 12


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except:
        return "127.0.0.1"
    finally:
        s.close()


def validate_password(pwd):
    """Sprawdza, czy hasło ma odpowiednią długość i tylko dozwolone znaki."""
    if not (MIN_PASSWORD_LENGTH <= len(pwd) <= MAX_PASSWORD_LENGTH):
        return False, f"długość musi być od {MIN_PASSWORD_LENGTH} do {MAX_PASSWORD_LENGTH}"
    if not all(c in CHARSET for c in pwd):
        return False, "niedozwolone znaki – tylko a-z, A-Z, 0-9"
    return True, ""


class DistributedBruteForcer:
    def __init__(self, initial_password=None):
        self.ip = get_local_ip()
        self.peers = {}  # ip -> last_seen
        self.done_batches = set()
        self.assigned_batches = {}  # ip -> (batch, last_seen)
        self.global_stop = False
        self.lock = threading.Lock()
        self.sync_ready = threading.Event()
        self.target_password = initial_password  # może być None
        self.target_hash = None
        self.is_leader = False
        self.password_length = None  # długość hasła do złamania

        print(f"[START] Node {self.ip}")

        # === MULTICAST ===
        self.mcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.mcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.mcast_sock.bind(("", MULTICAST_PORT))
        mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
        self.mcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # === TASK ===
        self.task_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.task_sock.bind(("", TASK_PORT))

        # === WĄTKI ===
        threading.Thread(target=self._multicast_listener, daemon=True).start()
        threading.Thread(target=self._task_listener, daemon=True).start()
        threading.Thread(target=self._send_ping, daemon=True).start()
        threading.Thread(target=self._send_sync_periodic, daemon=True).start()
        threading.Thread(target=self._cleanup, daemon=True).start()

        # === CZEKAJ NA SIEĆ LUB USTAL HASŁO ===
        self._establish_target_and_network()
        threading.Thread(target=self._work_loop, daemon=True).start()

    def _establish_target_and_network(self):
        print("[SYNC] Szukam istniejącej sieci...")
        self._send_sync_request()
        network_found = self.sync_ready.wait(SYNC_WAIT_TIMEOUT)

        if self.target_password is not None:
            # Uruchomiono Z hasłem – walidacja
            valid, err = validate_password(self.target_password)
            if not valid:
                print(f"[BŁĄD] Podane hasło: {err}!")
                sys.exit(1)

            if network_found:
                print("[INFO] Znaleziono sieć – anuluję własne hasło i dołączam do istniejącej.")
                self.target_password = None
                self.target_hash = None
                self.password_length = None
            else:
                print("[INFO] Brak sieci – tworzę nową z podanym hasłem.")
                self.target_hash = hashlib.sha1(self.target_password.encode()).hexdigest()
                self.password_length = len(self.target_password)
                self.is_leader = True
        else:
            # Uruchomiono BEZ hasła
            if network_found:
                print("[INFO] Dołączam do istniejącej sieci (łamanie wspólnego hasła).")
            else:
                # Pierwszy node bez hasła → wymuszamy podanie z walidacją
                print("[BŁĄD] Brak sieci i brak hasła – musisz podać hasło jako pierwszy!")
                while True:
                    pwd = input(f"Podaj hasło do złamania ({MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} znaków, tylko a-zA-Z0-9): ").strip()
                    valid, err = validate_password(pwd)
                    if valid:
                        self.target_password = pwd
                        self.target_hash = hashlib.sha1(pwd.encode()).hexdigest()
                        self.password_length = len(pwd)
                        self.is_leader = True
                        print(f"[INFO] Ustawiono hasło do złamania: {pwd} (dł: {self.password_length})")
                        break
                    else:
                        print(f"[BŁĄD] {err}")

        self._log_status()

    # === MULTICAST LISTENER ===
    def _multicast_listener(self):
        while not self.global_stop:
            try:
                data, addr = self.mcast_sock.recvfrom(1024)
                msg = data.decode()
                ip = addr[0]
                if ip == self.ip: continue

                with self.lock:
                    if ip not in self.peers:
                        print(f"[DISCOVER] nowy node: {ip}")
                    self.peers[ip] = time.time()

                if msg.startswith("PING:"):
                    pass

                elif msg.startswith("SYNC:"):
                    parts = msg[5:].split(":", 2)
                    csv = parts[0]
                    hash_part = parts[1] if len(parts) > 1 else ""
                    length_part = parts[2] if len(parts) > 2 else ""

                    done = {int(x) for x in csv.split(",") if x}
                    with self.lock:
                        old = len(self.done_batches)
                        self.done_batches |= done
                        if hash_part and self.target_hash is None:
                            self.target_hash = hash_part
                            self.password_length = int(length_part) if length_part else None
                            print(f"[SYNC] Otrzymano cel: SHA1 = {hash_part}, długość = {self.password_length}")
                            self.sync_ready.set()
                    if len(self.done_batches) > old:
                        print(f"[SYNC] Otrzymano {len(done)} paczek od {ip}")
                        self._log_status()
                        self.sync_ready.set()

            except Exception:
                continue

    def _send_ping(self):
        msg = f"PING:{self.ip}".encode()
        while not self.global_stop:
            try:
                self.mcast_sock.sendto(msg, (MULTICAST_GROUP, MULTICAST_PORT))
            except:
                pass
            time.sleep(PING_INTERVAL)

    def _send_sync_periodic(self):
        while not self.global_stop:
            time.sleep(SYNC_INTERVAL)
            self._broadcast_sync()

    def _broadcast_sync(self):
        with self.lock:
            csv = ",".join(map(str, sorted(self.done_batches)))
            hash_part = ""
            length_part = ""
            if self.is_leader or (self.target_hash and self.password_length is not None):
                hash_part = self.target_hash
                length_part = str(self.password_length)
            msg_parts = [f"SYNC:{csv}"]
            if hash_part:
                msg_parts.append(hash_part)
            if length_part:
                msg_parts.append(length_part)
            msg = ":".join(msg_parts).encode()
        try:
            self.mcast_sock.sendto(msg, (MULTICAST_GROUP, MULTICAST_PORT))
        except:
            pass

    def _send_sync_request(self):
        msg = b"SYNC_REQ:"
        for ip in list(self.peers.keys()):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.sendto(msg, (ip, TASK_PORT))
                s.close()
            except:
                pass

    # === TASK LISTENER ===
    def _task_listener(self):
        while not self.global_stop:
            try:
                data, addr = self.task_sock.recvfrom(4096)
                msg = data.decode()
                ip = addr[0]
                if ip == self.ip: continue

                with self.lock:
                    if ip not in self.peers:
                        print(f"[DISCOVER] node z TASK: {ip}")
                    self.peers[ip] = time.time()

                if msg.startswith("TASK_START:"):
                    _, b = msg.split(":", 1)
                    batch = int(b)
                    with self.lock:
                        self.assigned_batches[ip] = (batch, time.time())
                    print(f"[INFO] {ip} → paczka {batch}")
                    self._log_status()

                elif msg.startswith("TASK_DONE:"):
                    _, b = msg.split(":", 1)
                    batch = int(b)
                    with self.lock:
                        self.done_batches.add(batch)
                        self.assigned_batches.pop(ip, None)
                    print(f"[DONE] {ip} zakończył {batch}")
                    self._broadcast_sync()
                    self._log_status()

                elif msg.startswith("FOUND:"):
                    _, pwd = msg.split(":", 1)
                    print(f"\n[FOUND] Hasło: {pwd} (przez {ip})")
                    self.global_stop = True

                elif msg.startswith("SYNC_REQ:"):
                    self._broadcast_sync()

            except:
                continue

    def _send_to_all(self, msg):
        for ip in list(self.peers.keys()):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.5)
                s.sendto(msg.encode(), (ip, TASK_PORT))
                s.close()
            except:
                pass

    # === PRACA ===
    def _next_batch(self):
        with self.lock:
            b = 0
            while b in self.done_batches or any(v[0] == b for v in self.assigned_batches.values()):
                b += 1
            self.assigned_batches[self.ip] = (b, time.time())
            return b

    def _work_loop(self):
        while not self.global_stop and (self.target_hash is None or self.password_length is None):
            time.sleep(1)  # czekaj na hash i długość z sieci
        while not self.global_stop:
            batch = self._next_batch()
            print(f"[TASK] Biorę paczkę: {batch}")
            self._send_to_all(f"TASK_START:{batch}")

            start = batch * TASK_BATCH_SIZE
            found = self._process_batch(start)

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
        if self.password_length is None:
            return None
        total = len(CHARSET) ** self.password_length
        base = len(CHARSET)
        for i in range(TASK_BATCH_SIZE):
            if self.global_stop: return None
            idx = start_idx + i
            if idx >= total: return None
            pwd = ""
            x = idx
            for _ in range(self.password_length):
                pwd = CHARSET[x % base] + pwd
                x //= base
            if hashlib.sha1(pwd.encode()).hexdigest() == self.target_hash:
                return pwd
        return None

    # === CZYSZCZENIE ===
    def _cleanup(self):
        while not self.global_stop:
            time.sleep(5)
            now = time.time()
            with self.lock:
                dead = [ip for ip, t in self.peers.items() if now - t > TASK_TIMEOUT]
                for ip in dead:
                    del self.peers[ip]
                    self.assigned_batches.pop(ip, None)
                    print(f"[OFFLINE] {ip}")
            if dead:
                self._log_status()

    # === LOGI ===
    def _log_status(self):
        with self.lock:
            done = ", ".join(map(str, sorted(self.done_batches))) if self.done_batches else "brak"
            working = [f"{b} ({'ja' if ip==self.ip else ip})" for ip, (b,_) in self.assigned_batches.items()]
            work_str = ", ".join(working) if working else "brak"
            others = ", ".join(sorted(p for p in self.peers if p != self.ip))
            peers_str = others if others else "brak"
            target_info = f" (SHA1: {self.target_hash[:8]}..., dł: {self.password_length})" if self.target_hash and self.password_length else " (czekam na cel)"

        print(f"[STATUS] zrobione: {done}")
        print(f"[STATUS] robione: {work_str}")
        if peers_str != "brak":
            print(f"[STATUS] nody: {peers_str}")
        print(f"[STATUS] cel: {target_info}")


if __name__ == "__main__":
    # Obsługa argumentu z terminala
    initial_pwd = None
    if len(sys.argv) > 1:
        initial_pwd = sys.argv[1]
        valid, err = validate_password(initial_pwd)
        if not valid:
            print(f"[BŁĄD] Hasło z argumentu: {err}!")
            sys.exit(1)
        print(f"Uruchomiono z hasłem: {initial_pwd} (dł: {len(initial_pwd)})")

    node = DistributedBruteForcer(initial_password=initial_pwd)
    try:
        while not node.global_stop:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP]")
        node.global_stop = True