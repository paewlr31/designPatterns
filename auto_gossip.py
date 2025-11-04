import socket
import threading
import time
import ipaddress

BROADCAST_PORT = 50001
CHAT_PORT = 50002
DISCOVERY_INTERVAL = 3  # sekundy


def get_local_ip():
    """Zwraca lokalny adres IP w sieci Wi-Fi."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def get_broadcast_address(ip):
    """Zwraca adres broadcast w sieci (np. 192.168.1.255)."""
    try:
        net = ipaddress.ip_network(ip + "/24", strict=False)
        return str(net.broadcast_address)
    except Exception:
        return "255.255.255.255"


class P2PChat:
    def __init__(self):
        self.ip = get_local_ip()
        self.broadcast_ip = get_broadcast_address(self.ip)
        self.peers = set()
        print(f"[START] Twój adres IP to {self.ip}, broadcast: {self.broadcast_ip}")

        # Wątki
        threading.Thread(target=self._discover_peers, daemon=True).start()
        threading.Thread(target=self._listen_discovery, daemon=True).start()
        threading.Thread(target=self._listen_messages, daemon=True).start()

    # ======== ODKRYWANIE SĄSIADÓW ========
    def _discover_peers(self):
        """Wysyła broadcast HELLO do całej sieci."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        msg = f"HELLO:{self.ip}:{CHAT_PORT}".encode("utf-8")

        while True:
            try:
                sock.sendto(msg, (self.broadcast_ip, BROADCAST_PORT))
            except Exception as e:
                print(f"[WARN] Błąd przy wysyłaniu broadcastu: {e}")
            time.sleep(DISCOVERY_INTERVAL)

    def _listen_discovery(self):
        """Nasłuchuje broadcastów HELLO i odpowiada HELLO_BACK unicastowo."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except Exception:
            pass
        sock.bind(("", BROADCAST_PORT))

        while True:
            data, addr = sock.recvfrom(1024)
            text = data.decode("utf-8")
            if text.startswith("HELLO:"):
                _, ip, port = text.split(":")
                port = int(port)

                if ip != self.ip:
                    peer = (ip, port)
                    if peer not in self.peers:
                        self.peers.add(peer)
                        print(f"[DISCOVER] Znaleziono nowego peer'a: {peer}")

                    # Odpowiadamy bez broadcastu – direct do nadawcy
                    reply = f"HELLO_BACK:{self.ip}:{CHAT_PORT}".encode("utf-8")
                    sock.sendto(reply, (ip, BROADCAST_PORT))

            elif text.startswith("HELLO_BACK:"):
                _, ip, port = text.split(":")
                port = int(port)
                if ip != self.ip:
                    peer = (ip, port)
                    if peer not in self.peers:
                        self.peers.add(peer)
                        print(f"[DISCOVER_BACK] Peer potwierdził połączenie: {peer}")

    # ======== KOMUNIKACJA ========
    def _listen_messages(self):
        """Odbiera wiadomości czatu."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except Exception:
            pass
        sock.bind(("", CHAT_PORT))

        while True:
            try:
                data, addr = sock.recvfrom(4096)
                msg = data.decode("utf-8")
                print(f"\n[{addr[0]}] {msg}\n> ", end="")
            except Exception as e:
                print(f"[ERROR] Błąd odbioru: {e}")

    def send(self, message):
        """Wysyła wiadomość do wszystkich znanych peerów."""
        msg = message.encode("utf-8")
        for peer in list(self.peers):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(msg, peer)
                sock.close()
            except Exception as e:
                print(f"[ERROR] Nie mogę wysłać do {peer}: {e}")


if __name__ == "__main__":
    chat = P2PChat()
    print("[INFO] Wpisz wiadomość i naciśnij Enter.")
    try:
        while True:
            text = input("> ")
            chat.send(text)
    except KeyboardInterrupt:
        print("\n[STOP]")
