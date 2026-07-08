import json
import socket
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal


server_address = ("0.0.0.0", 5588)
recv_size = 65535
client_timeout = 15.0

MatchMode = Literal["quick", "friend"]


@dataclass
class Client:
    client_id: str
    address: tuple[str, int]
    mode: MatchMode
    password: str | None
    nickname: str
    last_seen: float
    room_id: str | None = None


@dataclass
class Room:
    room_id: str
    clients: tuple[Client, Client]


def json_bytes(message: dict[str, Any]) -> bytes:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()


def send_json(sock: socket.socket, message: dict[str, Any], address: tuple[str, int]) -> None:
    sock.sendto(json_bytes(message), address)


def recv_json(sock: socket.socket) -> tuple[dict[str, Any], tuple[str, int]]:
    data, address = sock.recvfrom(recv_size)
    message = json.loads(data.decode())
    if not isinstance(message, dict):
        raise ValueError("UDP message must be a JSON object.")
    return message, address


class MatchServer:
    def __init__(self) -> None:
        self.quick_waiting: list[Client] = []
        self.friend_waiting: dict[str, list[Client]] = {}
        self.clients_by_id: dict[str, Client] = {}
        self.client_ids_by_address: dict[tuple[str, int], str] = {}
        self.rooms: dict[str, Room] = {}

    def handle(self, sock: socket.socket, message: dict[str, Any], address: tuple[str, int]) -> None:
        msg_type = message.get("type")
        if msg_type == "join":
            self.join(sock, message, address)
        elif msg_type == "heartbeat":
            self.touch(message, address)
        elif msg_type == "leave":
            self.leave(sock, message, address)
        else:
            send_json(sock, {"type": "error", "message": f"Unknown message type: {msg_type}"}, address)

    def join(self, sock: socket.socket, message: dict[str, Any], address: tuple[str, int]) -> None:
        client_id = str(message.get("client_id") or uuid.uuid4().hex)
        mode = message.get("mode", "quick")
        password = message.get("password")
        nickname = str(message.get("nickname") or "Player").strip()[:16] or "Player"

        if mode not in ("quick", "friend"):
            send_json(sock, {"type": "error", "message": "mode must be 'quick' or 'friend'."}, address)
            return
        if mode == "friend" and not password:
            send_json(sock, {"type": "error", "message": "friend mode requires a password."}, address)
            return

        old_client = self.clients_by_id.get(client_id)
        if old_client is not None:
            self.remove_waiting(old_client)

        client = Client(
            client_id=client_id,
            address=address,
            mode=mode,
            password=str(password) if password is not None else None,
            nickname=nickname,
            last_seen=time.monotonic(),
        )
        self.clients_by_id[client_id] = client
        self.client_ids_by_address[address] = client_id

        print(f"- Join {mode}: {address}")
        if mode == "quick":
            self.quick_waiting.append(client)
            self.match_quick(sock)
        else:
            waiting = self.friend_waiting.setdefault(client.password or "", [])
            waiting.append(client)
            self.match_friend(sock, client.password or "")

        if client.room_id is None:
            send_json(sock, {"type": "waiting", "mode": mode}, address)

    def match_quick(self, sock: socket.socket) -> None:
        while len(self.quick_waiting) >= 2:
            c1 = self.quick_waiting.pop(0)
            c2 = self.quick_waiting.pop(0)
            self.create_room(sock, c1, c2)

    def match_friend(self, sock: socket.socket, password: str) -> None:
        waiting = self.friend_waiting.get(password)
        if waiting is None:
            return
        while len(waiting) >= 2:
            c1 = waiting.pop(0)
            c2 = waiting.pop(0)
            self.create_room(sock, c1, c2)
        if not waiting:
            self.friend_waiting.pop(password, None)

    def create_room(self, sock: socket.socket, c1: Client, c2: Client) -> None:
        room_id = uuid.uuid4().hex
        c1.room_id = room_id
        c2.room_id = room_id
        self.rooms[room_id] = Room(room_id=room_id, clients=(c1, c2))

        print(f"- Matched {c1.address} vs {c2.address} ({c1.mode})")
        self.send_matched(sock, c1, c2, "black")
        self.send_matched(sock, c2, c1, "white")

    def send_matched(self, sock: socket.socket, client: Client, peer: Client, role: str) -> None:
        send_json(
            sock,
            {
                "type": "matched",
                "room_id": client.room_id,
                "mode": client.mode,
                "role": role,
                "peer": {
                    "ip": peer.address[0],
                    "port": peer.address[1],
                    "nickname": peer.nickname,
                },
            },
            client.address,
        )

    def touch(self, message: dict[str, Any], address: tuple[str, int]) -> None:
        client = self.find_client(message, address)
        if client is not None:
            client.last_seen = time.monotonic()

    def leave(self, sock: socket.socket, message: dict[str, Any], address: tuple[str, int]) -> None:
        client = self.find_client(message, address)
        if client is None:
            return
        print(f"- Leave: {client.address}")
        self.disconnect(sock, client)

    def disconnect(self, sock: socket.socket, client: Client) -> None:
        if client.room_id is None:
            self.remove_waiting(client)
            self.remove_client(client)
            return

        room = self.rooms.pop(client.room_id, None)
        self.remove_client(client)
        if room is None:
            return

        for opponent in room.clients:
            if opponent.client_id == client.client_id:
                continue
            opponent.room_id = None
            self.remove_client(opponent)
            send_json(
                sock,
                {"type": "opponent_disconnected", "room_id": room.room_id, "result": "win"},
                opponent.address,
            )

    def remove_waiting(self, client: Client) -> None:
        if client.mode == "quick":
            self.quick_waiting = [waiting for waiting in self.quick_waiting if waiting.client_id != client.client_id]
            return

        if client.password is None:
            return
        waiting = self.friend_waiting.get(client.password)
        if waiting is None:
            return
        self.friend_waiting[client.password] = [
            waiting_client for waiting_client in waiting if waiting_client.client_id != client.client_id
        ]
        if not self.friend_waiting[client.password]:
            self.friend_waiting.pop(client.password, None)

    def remove_client(self, client: Client) -> None:
        self.clients_by_id.pop(client.client_id, None)
        self.client_ids_by_address.pop(client.address, None)

    def find_client(self, message: dict[str, Any], address: tuple[str, int]) -> Client | None:
        client_id = message.get("client_id")
        if isinstance(client_id, str):
            client = self.clients_by_id.get(client_id)
            if client is not None:
                return client

        client_id = self.client_ids_by_address.get(address)
        if client_id is None:
            return None
        return self.clients_by_id.get(client_id)

    def prune_timeouts(self, sock: socket.socket) -> None:
        now = time.monotonic()
        timed_out = [
            client for client in list(self.clients_by_id.values())
            if now - client.last_seen > client_timeout
        ]
        for client in timed_out:
            print(f"- Timeout: {client.address}")
            self.disconnect(sock, client)


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(server_address)
    sock.settimeout(0.2)
    server = MatchServer()

    try:
        print(f"UDP match server listening on {server_address[0]}:{server_address[1]}")
        while True:
            try:
                message, address = recv_json(sock)
                server.handle(sock, message, address)
            except socket.timeout:
                pass
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Invalid packet: {e}")
            server.prune_timeouts(sock)
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
