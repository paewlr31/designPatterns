import socket
import threading
import time
import hashlib
import string

# === USTAWIENIA ===
MULTICAST_GROUP = "224.0.0.251"
MULTICAST_PORT = 50001
TASK_PORT = 50002
PING_INTERVAL = 3
SYNC_INTERVAL = 8
TASK_BATCH_SIZE = 10000000
CHARSET = string.ascii_letters + string.digits
PASSWORD_LENGTH = 6
TASK_TIMEOUT = 30
SYNC_WAIT_TIMEOUT = 12

TARGET_HASH = hashlib.sha1(b"QwErT9").hexdigest()


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except:
        return "127.0.0.1"
    finally:
        s.close()


class DistributedBruteForcer:
    def __init__(self):
        self.ip = get_local_ip()
        self.peers = {}  # ip -> last_seen
        self.done_batches = set()
        self.assigned_batches = {}  # ip -> (batch, last_seen)
        self.global_stop = False
        self.lock = threading.Lock()
        self.sync_ready = threading.Event()

        print(f"[START] Node {self.ip}")

        # === MULTICAST SOCKET ===
        self.mcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.mcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.mcast_sock.bind(("", MULTICAST_PORT))
        mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
        self.mcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # === TASK SOCKET ===
        self.task_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.task_sock.bind(("", TASK_PORT))

        # === WĄTKI ===
        threading.Thread(target=self._multicast_listener, daemon=True).start()
        threading.Thread(target=self._task_listener, daemon=True).start()
        threading.Thread(target=self._send_ping, daemon=True).start()
        threading.Thread(target=self._send_sync_periodic, daemon=True).start()
        threading.Thread(target=self._cleanup, daemon=True).start()

        # === CZEKAJ NA SIEĆ ===
        self._wait_for_network()
        threading.Thread(target=self._work_loop, daemon=True).start()

    def _wait_for_network(self):
        print("[SYNC] Czekam na sieć (max 12s)...")
        self._send_sync_request()
        if not self.sync_ready.wait(SYNC_WAIT_TIMEOUT):
            print("[SYNC] Timeout – startuję lokalnie.")
        else:
            print(f"[SYNC] Połączono! Znam {len(self.done_batches)} paczek.")
        self._log_status()

    # === MULTICAST: PING + SYNC + HELLO ===
    def _multicast_listener(self):
        while not self.global_stop:
            try:
                data, addr = self.mcast_sock.recvfrom(1024)
                msg = data.decode()
                ip = addr[0]
                if ip == self.ip: continue

                with self.lock:
                    self.peers[ip] = time.time()

                if msg.startswith("PING:"):
                    pass  # tylko aktualizacja

                elif msg.startswith("SYNC:"):
                    _, csv = msg.split(":", 1)
                    done = {int(x) for x in csv.split(",") if x}
                    with self.lock:
                        old = len(self.done_batches)
                        self.done_batches |= done
                    if len(self.done_batches) > old:
                        print(f"[SYNC] Otrzymano {len(done)} paczek od {ip}")
                        self._log_status()
                        self.sync_ready.set()

            except:
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
        msg = f"SYNC:{csv}".encode()
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

    # === TASK COMMUNICATION ===
    def _task_listener(self):
        while not self.global_stop:
            try:
                data, addr = self.task_sock.recvfrom(4096)
                msg = data.decode()
                ip = addr[0]
                if ip == self.ip: continue

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
        total = len(CHARSET) ** PASSWORD_LENGTH
        base = len(CHARSET)
        for i in range(TASK_BATCH_SIZE):
            if self.global_stop: return None
            idx = start_idx + i
            if idx >= total: return None
            pwd = ""
            x = idx
            for _ in range(PASSWORD_LENGTH):
                pwd = CHARSET[x % base] + pwd
                x //= base
            if hashlib.sha1(pwd.encode()).hexdigest() == TARGET_HASH:
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

        print(f"[STATUS] zrobione: {done}")
        print(f"[STATUS] robione: {work_str}")
        if peers_str != "brak":
            print(f"[STATUS] nody: {peers_str}")


if __name__ == "__main__":
    node = DistributedBruteForcer()
    try:
        while not node.global_stop:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP]")
        node.global_stop = True