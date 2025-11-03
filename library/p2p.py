# library/p2p.py
import socket
import json
import threading
import time
import uuid
from typing import Dict, Optional, Any
from dataclasses import dataclass

BROADCAST_IP = "255.255.255.255"
PORT = 5005
BUFFER = 8192

@dataclass
class ChunkState:
    status: str = "todo"        # "todo", "doing", "done"
    worker: Optional[str] = None
    result: Optional[str] = None  # hasło lub None

class P2PNode:
    def __init__(self, node_id: Optional[str] = None):
        self.node_id = node_id or str(uuid.uuid4())[:8]
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.settimeout(1.0)
        self.sock.bind(('', PORT))
        self.ip = self._get_my_ip()

        # --- stan globalny (współdzielony przez broadcast) ---
        self.total_chunks = 0
        self.chunks: Dict[int, ChunkState] = {}  # chunk_id -> ChunkState
        self.nodes: Dict[str, str] = {}          # node_id -> ip
        self.lock = threading.Lock()

        # --- flaga zakończenia ---
        self.password_found = False
        self.found_password = None

        print(f"[NODE {self.node_id}] IP: {self.ip}")

    def _get_my_ip(self) -> str:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"
        finally:
            s.close()

    def send(self, msg_type: str, data: Dict[str, Any] = None):
        payload = {
            "type": msg_type,
            "from": self.node_id,
            "ip": self.ip,
            "ts": time.time()
        }
        if data:
            payload.update(data)
        try:
            self.sock.sendto(json.dumps(payload).encode('utf-8'), (BROADCAST_IP, PORT))
        except:
            pass

    def start(self):
        threading.Thread(target=self._listener, daemon=True).start()
        time.sleep(0.5)
        self.send("HELLO")
        print(f"[LOG] Node {self.node_id} dołączył do sieci")

    def _listener(self):
        while not self.password_found:
            try:
                data, _ = self.sock.recvfrom(BUFFER)
                msg = json.loads(data.decode('utf-8'))
                self._handle(msg)
            except socket.timeout:
                continue
            except:
                break

    def _handle(self, msg: Dict):
        typ = msg.get("type")
        sender = msg.get("from")
        sender_ip = msg.get("ip")

        with self.lock:
            self.nodes[sender] = sender_ip

            if typ == "HELLO":
                print(f"[LOG] Node {sender} ({sender_ip}) dołączył")
                self._broadcast_state()

            elif typ == "BYE":
                print(f"[LOG] Node {sender} ({sender_ip}) wyszedł")
                self.nodes.pop(sender, None)
                # zwolnij jego paczki
                for cid, state in self.chunks.items():
                    if state.worker == sender:
                        state.status = "todo"
                        state.worker = None
                self._broadcast_state()

            elif typ == "STATE":
                self._merge_state(msg)

            elif typ == "CHUNK_TAKE":
                cid = msg.get("chunk_id")
                if cid in self.chunks and self.chunks[cid].status == "todo":
                    self.chunks[cid].status = "doing"
                    self.chunks[cid].worker = sender
                    self._broadcast_state()

            elif typ == "CHUNK_DONE":
                cid = msg.get("chunk_id")
                found = msg.get("found")
                password = msg.get("password")
                if cid in self.chunks:
                    self.chunks[cid].status = "done"
                    self.chunks[cid].result = password
                    print(f"[LOG] Paczka #{cid+1} zakończona → {'ZNALEZIONO' if found else 'nie znaleziono'}")
                    if found:
                        self.password_found = True
                        self.found_password = password
                        self.send("PASS_FOUND", {"password": password})
                    self._broadcast_state()

            elif typ == "PASS_FOUND":
                password = msg.get("password")
                print(f"[LOG] HASŁO ZNALEZIONE: {password} → kończę pracę")
                self.password_found = True
                self.found_password = password

    def _broadcast_state(self):
        state = {
            "total_chunks": self.total_chunks,
            "chunks": {cid: {
                "status": s.status,
                "worker": s.worker,
                "result": s.result
            } for cid, s in self.chunks.items()}
        }
        self.send("STATE", state)

    def _merge_state(self, msg: Dict):
        remote_chunks = msg.get("chunks", {})
        changed = False
        for cid, rs in remote_chunks.items():
            cid = int(cid)
            if cid not in self.chunks:
                self.chunks[cid] = ChunkState(
                    status=rs["status"],
                    worker=rs["worker"],
                    result=rs["result"]
                )
                changed = True
            else:
                local = self.chunks[cid]
                # nowszy stan? używamy nowszego timestampu (msg ma "ts")
                # prosta zasada: "doing" > "todo", "done" > wszystko
                if rs["status"] == "done" and local.status != "done":
                    local.status = "done"
                    local.result = rs["result"]
                    changed = True
                elif rs["status"] == "doing" and local.status == "todo":
                    local.status = "doing"
                    local.worker = rs["worker"]
                    changed = True
        if changed:
            self._broadcast_state()

    def initialize_chunks(self, total: int):
        with self.lock:
            if self.total_chunks == 0:
                self.total_chunks = total
                self.chunks = {i: ChunkState() for i in range(total)}
                print(f"[INIT] Utworzono {total} paczek")
                self._broadcast_state()

    def take_next_chunk(self) -> Optional[int]:
        with self.lock:
            for cid, state in self.chunks.items():
                if state.status == "todo":
                    state.status = "doing"
                    state.worker = self.node_id
                    self.send("CHUNK_TAKE", {"chunk_id": cid})
                    print(f"[LOG] Biorę paczkę #{cid+1}")
                    return cid
            return None

    def report_done(self, chunk_id: int, found: bool, password: Optional[str]):
        self.send("CHUNK_DONE", {
            "chunk_id": chunk_id,
            "found": found,
            "password": password
        })

    def goodbye(self):
        self.send("BYE")
        time.sleep(0.3)
        self.sock.close()