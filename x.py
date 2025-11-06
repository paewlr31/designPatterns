#!/usr/bin/env python3
import socket
import threading
import time
import hashlib
import string
import argparse
import re
import sys

# === USTAWIENIA ===
MULTICAST_GROUP = "224.0.0.251"
MULTICAST_PORT = 50001
TASK_PORT = 50002
PING_INTERVAL = 3
SYNC_INTERVAL = 8
TASK_BATCH_SIZE = 1000000
CHARSET = string.ascii_letters + string.digits
PASSWORD_MIN = 4
PASSWORD_MAX = 7
TASK_TIMEOUT = 30
SYNC_WAIT_TIMEOUT = 12

# === POMOCNICZE ===
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except:
        return "127.0.0.1"
    finally:
        s.close()

def valid_password(pwd: str):
    if not (PASSWORD_MIN <= len(pwd) <= PASSWORD_MAX):
        return False, f"Hasło musi mieć długość między {PASSWORD_MIN} a {PASSWORD_MAX} znaków."
    if not re.fullmatch(r"[A-Za-z0-9]+", pwd):
        return False, "Hasło zawiera niedozwolone znaki — dozwolone: a-zA-Z0-9."
    return True, ""

class DistributedBruteForcer:
    def __init__(self, provided_password=None):
        self.ip = get_local_ip()
        self.peers = {}  # ip -> last_seen
        self.done_batches = set()
        self.assigned_batches = {}  # ip -> (batch, last_seen)
        self.global_stop = False
        self.lock = threading.Lock()
        self.sync_ready = threading.Event()

        # target hash (sha1 hex) do łamania, ustalane przez sieć lub przez pierwszy węzeł
        self.target_hash = None
        self.hash_ready = threading.Event()

        # proposed password (jeśli użytkownik podał przy starcie)
        self.proposed_password = None
        self.proposed_hash = None
        if provided_password is not None:
            ok, msg = valid_password(provided_password)
            if not ok:
                print(f"[BŁĄD] Nieprawidłowe hasło przy starcie: {msg}")
                sys.exit(1)
            self.proposed_password = provided_password
            self.proposed_hash = hashlib.sha1(provided_password.encode()).hexdigest()

        print(f"[START] Node {self.ip}")

        # === MULTICAST ===
        self.mcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.mcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.mcast_sock.bind(("", MULTICAST_PORT))
        except Exception as e:
            print(f"[FATAL] Nie udało się zbindować multicast portu {MULTICAST_PORT}: {e}")
            sys.exit(1)
        mreq = socket.inet_aton(MULTICAST_GROUP) + socket.inet_aton("0.0.0.0")
        self.mcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # === TASK ===
        self.task_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.task_sock.bind(("", TASK_PORT))
        except Exception as e:
            print(f"[FATAL] Nie udało się zbindować task portu {TASK_PORT}: {e}")
            sys.exit(1)

        # === WĄTKI LISTENERÓW I SERWISÓW ===
        threading.Thread(target=self._multicast_listener, daemon=True).start()
        threading.Thread(target=self._task_listener, daemon=True).start()
        threading.Thread(target=self._send_ping, daemon=True).start()
        threading.Thread(target=self._send_sync_periodic, daemon=True).start()
        threading.Thread(target=self._cleanup, daemon=True).start()

        # --- NAPRAWA: uruchamiamy _work_loop wcześniej, żeby działał mimo blokującego input() ---
        threading.Thread(target=self._work_loop, daemon=True).start()

        # === CZEKAJ (może blokować input) ===
        self._wait_for_network()
        # (uwaga: wątek pracy już wystartowany powyżej)

    # === START / SYNC LOGIKA (poprawiona) ===
    def _wait_for_network(self):
        """
        Logika startowa:
        - wysyłamy prośbę o sync do znanych peerów
        - czekamy SPECJALNIE na HASH_SET (hash sieci) przez SYNC_WAIT_TIMEOUT
        - jeśli otrzymamy hash -> adoptujemy i startujemy
        - jeśli nie otrzymamy hashu:
            - jeśli podano hasło przy starcie -> tworzymy sieć i rozgłaszamy hash
            - jeśli nie podano hasła i nie mamy peerów -> wymagamy podania hasła interaktywnie
            - jeśli nie podano hasła, ale mamy peerów (sieć bez hashu) -> czekamy krótko jeszcze raz, potem prosimy o hasło
        """
        print("[SYNC] Inicjuję wykrywanie sieci i czekam na HASH_SET (max {}s)...".format(SYNC_WAIT_TIMEOUT))
        # wyślij prośby o sync (jeśli mamy peerów)
        self._send_sync_request()

        # pierwsze czekanie na hash
        got_hash = self.hash_ready.wait(SYNC_WAIT_TIMEOUT)

        if got_hash:
            print("[SYNC] Otrzymano hash od sieci — dołączam do istniejącej sieci.")
            # jeżeli użytkownik podał hasło przy starcie -> anulujemy lokalne (zgodnie z wymaganiem)
            if self.proposed_password:
                print("[INFO] Podałeś hasło przy starcie, ale znaleziono sieć. Anuluję swoje hasło i dołączam do sieci.")
                self.proposed_password = None
                self.proposed_hash = None
            self.sync_ready.set()
            self._log_status()
            return

        # nie otrzymaliśmy hashu w pierwszym timeoutcie
        with self.lock:
            peers_count = len(self.peers)

        if self.proposed_password:
            # Mamy podane hasło i nie widzimy hash'u -> tworzymy sieć własną
            self.target_hash = self.proposed_hash
            self.hash_ready.set()
            print("[SYNC] Nie wykryto sieci z hashem — tworzę sieć z podanym hasłem.")
            self._broadcast_hash_set(self.target_hash)
            self.sync_ready.set()
            self._log_status()
            return

        # brak podanego hasła przy starcie
        if peers_count == 0:
            # brak peerów -> jesteśmy pierwsi => wymagamy hasła interakcyjnie
            print("[SYNC] Brak istniejącej sieci i brak podanego hasła. Proszę podać hasło (4-7 znaków, a-zA-Z0-9).")
            while True:
                try:
                    pwd = input("Podaj hasło do ustawienia sieci: ").strip()
                except EOFError:
                    print("\n[STOP] Wejście przerwane.")
                    self.global_stop = True
                    return
                ok, msg = valid_password(pwd)
                if not ok:
                    print(f"[BŁĄD] {msg} Spróbuj ponownie.")
                    continue
                self.proposed_password = pwd
                self.proposed_hash = hashlib.sha1(pwd.encode()).hexdigest()
                self.target_hash = self.proposed_hash
                self.hash_ready.set()
                print("[SYNC] Ustawiono hasło i tworzymy sieć.")
                self._broadcast_hash_set(self.target_hash)
                self.sync_ready.set()
                break
            self._log_status()
            return

        # mamy peerów ale nie otrzymaliśmy hashu -> może ktoś startuje i nie zdążył rozgłosić
        print("[SYNC] Wykryto peerów, ale brak HASH_SET. Daję sieci jeszcze {}s na rozgłoszenie hashu...".format(SYNC_WAIT_TIMEOUT))
        got_hash2 = self.hash_ready.wait(SYNC_WAIT_TIMEOUT)
        if got_hash2:
            print("[SYNC] Otrzymano hash od sieci w drugim oknie — dołączam.")
            self.sync_ready.set()
            if self.proposed_password:
                print("[INFO] Podałeś hasło przy starcie, ale znaleziono sieć. Anuluję swoje hasło i dołączam do sieci.")
                self.proposed_password = None
                self.proposed_hash = None
            self._log_status()
            return
        # dalej brak hashu -> prosimy o hasło (unika deadlocka)
        print("[SYNC] Po dłuższym oczekiwaniu nie otrzymano hashu. Proszę podać hasło (4-7 znaków, a-zA-Z0-9).")
        while True:
            try:
                pwd = input("Podaj hasło do ustawienia sieci: ").strip()
            except EOFError:
                print("\n[STOP] Wejście przerwane.")
                self.global_stop = True
                return
            ok, msg = valid_password(pwd)
            if not ok:
                print(f"[BŁĄD] {msg} Spróbuj ponownie.")
                continue
            self.proposed_password = pwd
            self.proposed_hash = hashlib.sha1(pwd.encode()).hexdigest()
            self.target_hash = self.proposed_hash
            self.hash_ready.set()
            print("[SYNC] Ustawiono hasło i tworzymy sieć.")
            self._broadcast_hash_set(self.target_hash)
            self.sync_ready.set()
            break
        self._log_status()

    # === MULTICAST LISTENER ===
    def _multicast_listener(self):
        while not self.global_stop:
            try:
                data, addr = self.mcast_sock.recvfrom(4096)
                msg = data.decode()
                ip = addr[0]
                if ip == self.ip:
                    continue

                # DODAJ PEERA PO PING LUB SYNC
                with self.lock:
                    if ip not in self.peers:
                        print(f"[DISCOVER] nowy node (multicast): {ip}")
                    self.peers[ip] = time.time()

                if msg.startswith("PING:"):
                    # nic więcej — tylko obecność
                    pass

                elif msg.startswith("SYNC:"):
                    _, csv = msg.split(":", 1)
                    done = {int(x) for x in csv.split(",") if x}
                    with self.lock:
                        old = len(self.done_batches)
                        self.done_batches |= done
                    if len(self.done_batches) > old:
                        print(f"[SYNC] Otrzymano {len(done)} paczek od {ip}")
                        self._log_status()
                    # zauważenie SYNC oznacza, że jest jakaś sieć — ustawiamy sync_ready (ale nie hash_ready!)
                    self.sync_ready.set()

                elif msg.startswith("HASH_SET:"):
                    _, h = msg.split(":", 1)
                    h = h.strip()
                    if h:
                        # ustaw hash sieci jeśli jeszcze nie ustawiony lub jest inny (nadpisujemy)
                        if self.target_hash != h:
                            print(f"[HASH] Otrzymano hash hasła od {ip}. Ustawiam hash sieci.")
                        self.target_hash = h
                        self.hash_ready.set()
                        # również oznacz sieć istniejacą
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
            # jeśli mamy ustawiony hash to okresowo go rozgłaszamy, by nowi/po powrocie go odebrali
            if self.target_hash:
                self._broadcast_hash_set(self.target_hash)

    def _broadcast_sync(self):
        with self.lock:
            csv = ",".join(map(str, sorted(self.done_batches)))
        msg = f"SYNC:{csv}".encode()
        try:
            self.mcast_sock.sendto(msg, (MULTICAST_GROUP, MULTICAST_PORT))
        except:
            pass

    def _broadcast_hash_set(self, hexhash):
        msg = f"HASH_SET:{hexhash}".encode()
        try:
            self.mcast_sock.sendto(msg, (MULTICAST_GROUP, MULTICAST_PORT))
            print("[HASH] Rozgłosiłem hash hasła do sieci.")
        except:
            pass

    def _send_sync_request(self):
        # Wyślij prośbę o sync do znanych peerów (puste jeśli jeszcze nie mamy)
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
                if ip == self.ip:
                    continue

                # DODAJ PEERA PO TASK_START
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
                    # rozgłoś update o zrobionych paczkach
                    self._broadcast_sync()
                    self._log_status()

                elif msg.startswith("FOUND:"):
                    _, pwd = msg.split(":", 1)
                    print(f"\n[FOUND] Hasło: {pwd} (przez {ip})")
                    self.global_stop = True

                elif msg.startswith("SYNC_REQ:"):
                    self._broadcast_sync()

            except Exception:
                continue

    def _send_to_all(self, msg):
        # WYSYŁA DO KAŻDEGO ZNANYM PEERA (TASK_PORT)
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
        # Najpierw upewnij się, że mamy hash do łamania
        print("[WORK] Czekam na hash hasła, żeby rozpocząć pracę...")
        # Zaczekaj aż hash zostanie ustawiony (np. przez lidera) — niekończąco; jeśli program ma być przerwany, global_stop przerwie pętle
        while not self.global_stop and not self.hash_ready.is_set():
            time.sleep(0.5)
        if self.global_stop:
            return
        print("[WORK] Hash dostępny — zaczynam pracę.")
        # Główna pętla pracy
        while not self.global_stop:
            # Zanim pobierzemy paczkę sprawdźmy czy target_hash dalej istnieje
            if not self.target_hash:
                print("[WORK] Utracono hash sieci — czekam na ponowne ustawienie.")
                self.hash_ready.clear()
                while not self.hash_ready.is_set() and not self.global_stop:
                    time.sleep(0.5)
                continue

            batch = self._next_batch()
            print(f"[TASK] Biorę paczkę: {batch}")
            # Ogłaszamy innym, że zaczęliśmy paczkę
            self._send_to_all(f"TASK_START:{batch}")

            start = batch * TASK_BATCH_SIZE
            found = self._process_batch(start)

            if found:
                # odnaleziono hasło
                self.global_stop = True
                self._send_to_all(f"FOUND:{found}")
                print(f"[FOUND] Znalazłem: {found}")
                break
            else:
                # zakończono paczkę
                with self.lock:
                    self.done_batches.add(batch)
                    self.assigned_batches.pop(self.ip, None)
                self._send_to_all(f"TASK_DONE:{batch}")
                self._broadcast_sync()
                self._log_status()

    def _process_batch(self, start_idx):
        # Przetwarzamy paczkę: generujemy hasła i porównujemy sha1
        base = len(CHARSET)

        # Precompute total count of combos for lengths PASSWORD_MIN..PASSWORD_MAX
        lengths = list(range(PASSWORD_MIN, PASSWORD_MAX + 1))
        counts = [base ** L for L in lengths]
        total_true = sum(counts)

        for i in range(TASK_BATCH_SIZE):
            if self.global_stop:
                return None
            idx = start_idx + i
            if idx >= total_true:
                return None
            # Map idx to (length, offset)
            offset = idx
            chosen_len = None
            for L, c in zip(lengths, counts):
                if offset < c:
                    chosen_len = L
                    break
                offset -= c
            if chosen_len is None:
                return None
            # build password of length chosen_len from offset
            x = offset
            pwd_chars = []
            for _ in range(chosen_len):
                pwd_chars.append(CHARSET[x % base])
                x //= base
            pwd = "".join(reversed(pwd_chars))
            # compare
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
            th = self.target_hash if self.target_hash else "brak"

        print(f"[STATUS] zrobione: {done}")
        print(f"[STATUS] robione: {work_str}")
        print(f"[STATUS] nody: {peers_str}")
        print(f"[STATUS] target_hash: {th}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed brute forcer — uruchom z opcjonalnym --password")
    parser.add_argument("--password", "-p", help="Opcjonalne hasło (4-7 znaków, a-zA-Z0-9) — jeśli podasz i znajdzie się sieć, Twoje hasło zostanie anulowane i dołączysz do istniejącej sieci.", default=None)
    args = parser.parse_args()

    node = DistributedBruteForcer(provided_password=args.password)
    try:
        while not node.global_stop:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP] Ctrl-C")
        node.global_stop = True
        time.sleep(0.2)
