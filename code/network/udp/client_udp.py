import json
import os.path
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal


SERVER_PORT = 5588
RECV_SIZE = 65535
HEARTBEAT_INTERVAL = 5.0
CONNECT_TIMEOUT = 120.0
RETRY_INTERVAL = 0.25

MatchMode = Literal["quick", "friend"]


@dataclass
class MatchInfo:
    peer_ip: str
    peer_port: int
    peer_nickname: str
    room_id: str
    role: str
    mode: MatchMode


@dataclass
class PendingMessage:
    message: dict[str, Any]
    last_sent: float


def _read_server_address(server_list: str) -> tuple[str, int]:
    rendezvous = None
    server_list_file = os.path.join(os.path.dirname(__file__), server_list)
    with open(server_list_file, "r") as f:
        for line in f.readlines():
            line = line.split("#")[0].strip()
            if line:
                rendezvous = (socket.gethostbyname(line), SERVER_PORT)

    if rendezvous is None:
        raise FileNotFoundError(server_list + " is empty.")
    return rendezvous


def _make_socket() -> socket.socket:
    for port in range(56456, 60000):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", port))
            sock.settimeout(0.2)
            return sock
        except OSError:
            sock.close()
    raise RuntimeError("Failed to bind to any available port.")


def _json_bytes(message: dict[str, Any]) -> bytes:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()


def _send_json(sock: socket.socket, message: dict[str, Any], address: tuple[str, int]) -> None:
    sock.sendto(_json_bytes(message), address)


def _recv_json(sock: socket.socket) -> tuple[dict[str, Any], tuple[str, int]]:
    data, address = sock.recvfrom(RECV_SIZE)
    message = json.loads(data.decode())
    if not isinstance(message, dict):
        raise ValueError("UDP message must be a JSON object.")
    return message, address


def connect_server(
    server_list: str = "../server_list.txt",
    mode: MatchMode = "quick",
    password: str | None = None,
    nickname: str = "Player",
) -> tuple[socket.socket, tuple[str, int], MatchInfo]:
    if mode not in ("quick", "friend"):
        raise ValueError("mode must be either 'quick' or 'friend'.")
    if mode == "friend" and not password:
        raise ValueError("friend mode requires a password.")

    rendezvous = _read_server_address(server_list)
    sock = _make_socket()
    client_id = uuid.uuid4().hex
    joined_at = time.monotonic()
    last_heartbeat = 0.0

    join_message = {
        "type": "join",
        "client_id": client_id,
        "mode": mode,
        "password": password,
        "nickname": nickname,
    }
    _send_json(sock, join_message, rendezvous)

    print("checked in with server, waiting")
    while True:
        now = time.monotonic()
        if now - joined_at > CONNECT_TIMEOUT:
            _send_json(sock, {"type": "leave", "client_id": client_id}, rendezvous)
            sock.close()
            raise TimeoutError("Timed out while waiting for a match.")

        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            _send_json(sock, {"type": "heartbeat", "client_id": client_id}, rendezvous)
            last_heartbeat = now

        try:
            message, _address = _recv_json(sock)
        except socket.timeout:
            continue

        msg_type = message.get("type")
        if msg_type == "matched":
            peer = message["peer"]
            match = MatchInfo(
                peer_ip=peer["ip"],
                peer_port=int(peer["port"]),
                peer_nickname=str(peer.get("nickname", "Opponent")),
                room_id=message["room_id"],
                role=message["role"],
                mode=message["mode"],
            )
            _send_json(sock, {"type": "punch", "room_id": match.room_id}, (match.peer_ip, match.peer_port))
            print("ready to exchange messages\n")
            return sock, rendezvous, match
        if msg_type == "error":
            sock.close()
            raise RuntimeError(str(message.get("message", "Server rejected the connection.")))


class OmokUDP:
    def __init__(
        self,
        mode: MatchMode = "quick",
        password: str | None = None,
        nickname: str = "Player",
        server_list: str = "../server_list.txt",
    ) -> None:
        self.nickname = nickname
        self.sock, self.server_address, self.match = connect_server(server_list, mode, password, nickname)
        self.peer_address = (self.match.peer_ip, self.match.peer_port)
        self.peer_nickname = self.match.peer_nickname
        self.room_id = self.match.room_id
        self.role = self.match.role
        self.mode = self.match.mode

        self.running = False
        self._closed = False
        self.stop_event = threading.Event()
        self.listener: threading.Thread | None = None
        self.heartbeat_thread: threading.Thread | None = None
        self.retry_thread: threading.Thread | None = None
        self.pending_messages: dict[str, PendingMessage] = {}
        self.seen_message_ids: set[str] = set()
        self.reliable_lock = threading.Lock()

        self.rx_event: Callable[[dict[str, Any]], None] = lambda data: print(f"peer: {data}")
        self.status_event: Callable[[dict[str, Any]], None] = lambda data: print(f"status: {data}")

    def start_listen(self) -> None:
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.listener = threading.Thread(target=self._listen, daemon=True)
        self.heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.retry_thread = threading.Thread(target=self._retry_pending_messages, daemon=True)
        self.listener.start()
        self.heartbeat_thread.start()
        self.retry_thread.start()

    def _listen(self) -> None:
        while self.running:
            try:
                message, address = _recv_json(self.sock)
            except socket.timeout:
                continue
            except (OSError, json.JSONDecodeError, ValueError):
                if self.running:
                    self.status_event({"type": "error", "message": "Invalid UDP packet received."})
                continue

            msg_type = message.get("type")
            if address == self.server_address:
                self._handle_server_message(message)
            elif msg_type == "punch":
                continue
            elif msg_type == "ack":
                self._handle_ack(message)
            elif msg_type == "leave":
                self.status_event({"type": "opponent_disconnected", "result": "win"})
            else:
                if self._is_duplicate_reliable_message(message):
                    continue
                self.rx_event(message)

    def _handle_server_message(self, message: dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type == "opponent_disconnected":
            self.status_event(message)
        elif msg_type == "error":
            self.status_event(message)

    def _heartbeat(self) -> None:
        while self.running:
            try:
                self._send_server({"type": "heartbeat"})
            except OSError:
                break
            self.stop_event.wait(HEARTBEAT_INTERVAL)

    def _retry_pending_messages(self) -> None:
        while self.running:
            now = time.monotonic()
            with self.reliable_lock:
                pending_messages = list(self.pending_messages.values())

            for pending in pending_messages:
                if now - pending.last_sent < RETRY_INTERVAL:
                    continue
                try:
                    _send_json(self.sock, pending.message, self.peer_address)
                except OSError:
                    break
                with self.reliable_lock:
                    current = self.pending_messages.get(str(pending.message.get("id")))
                    if current is pending:
                        current.last_sent = now

            self.stop_event.wait(RETRY_INTERVAL)

    def _send_server(self, message: dict[str, Any]) -> None:
        message.setdefault("room_id", self.room_id)
        _send_json(self.sock, message, self.server_address)

    def _send_peer_unreliable(self, message: dict[str, Any]) -> None:
        message.setdefault("room_id", self.room_id)
        _send_json(self.sock, message, self.peer_address)

    def _handle_ack(self, message: dict[str, Any]) -> None:
        ack_id = message.get("ack_id")
        if not isinstance(ack_id, str):
            return
        with self.reliable_lock:
            self.pending_messages.pop(ack_id, None)

    def _is_duplicate_reliable_message(self, message: dict[str, Any]) -> bool:
        message_id = message.get("id")
        if not isinstance(message_id, str):
            return False

        self._send_peer_unreliable({"type": "ack", "ack_id": message_id})
        with self.reliable_lock:
            if message_id in self.seen_message_ids:
                return True
            self.seen_message_ids.add(message_id)
        return False

    def send(self, message: dict[str, Any], reliable: bool = True) -> None:
        message.setdefault("room_id", self.room_id)
        if not reliable:
            _send_json(self.sock, message, self.peer_address)
            return

        message_id = str(message.get("id") or uuid.uuid4().hex)
        message["id"] = message_id
        now = time.monotonic()
        with self.reliable_lock:
            self.pending_messages[message_id] = PendingMessage(message=message.copy(), last_sent=now)
        _send_json(self.sock, message, self.peer_address)

    def send_move(self, x: int, y: int) -> None:
        self.send({"type": "move", "x": x, "y": y})

    def send_chat(self, text: str) -> None:
        self.send({"type": "chat", "message": text})

    def close(self, notify: bool = True) -> None:
        if self._closed:
            return
        self._closed = True
        self.running = False
        self.stop_event.set()

        if notify:
            try:
                self.send({"type": "leave"})
                self._send_server({"type": "leave"})
            except OSError:
                pass

        self.sock.close()
        current_thread = threading.current_thread()
        for thread in (self.listener, self.heartbeat_thread, self.retry_thread):
            if thread is not None and thread is not current_thread and thread.is_alive():
                thread.join(timeout=0.5)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
