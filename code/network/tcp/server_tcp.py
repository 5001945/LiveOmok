# TCP server: https://itholic.github.io/python-socket/
import typing
from typing import TYPE_CHECKING, cast
import argparse
import socket
import threading
import time
import select
import json

if TYPE_CHECKING:
    class ArgsData:
        ip: str
        port: int
        buf_size: int
        # room_size: int

class Room:
    def __init__(self, room_name: str) -> None:
        self.name = room_name
        self.description = ""
        self.locked = True
        self.password = ""
        self.connections = list[ChatSocket]()
        self.max_connections = 12
        self.players = list[ChatSocket]()

    def add(self, conn: 'ChatSocket'):
        conn.room = self
        self.connections.append(conn)
    
    def remove(self, conn: 'ChatSocket') -> bool:
        if conn not in self.connections:
            return False
        self.connections.remove(conn)
        if conn in self.players:
            self.players.remove(conn)
        return True
    
    @property
    def host(self):
        if self.connections:
            return self.connections[0]
        else:
            return None


class ChatSocket:
    def __init__(self, connection: socket.socket, name: str, room: Room | None, event: typing.Callable[['ChatSocket'], None]) -> None:
        self.socket = connection
        self.name = name
        self.room = room

        self.event_thread = threading.Thread(target=event, args=(self,))
        self.event_thread.start()
    #     self.heartbeat_thread = threading.Thread(target=self._heartbeat)
    #     self.heartbeat_thread.start()

    # def _heartbeat(self):
    #     while True:
    #         time.sleep(0.5)
    #         self.socket.sendall("HEARTBEAT".encode())


class RoomManager:
    def __init__(self, args: 'ArgsData') -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # TCP
        self.sock.bind((args.ip, args.port))
        self.sock.listen()  # Ready for client

        self.buf_size = args.buf_size
        self.rooms: dict[str, Room] = {}

    def run(self):
        while True:
            conn, addr = self.sock.accept()  # Block until new connection has made
            greeting = conn.recv(self.buf_size).decode()
            print(greeting)
            if greeting != "HELLO":
                conn.shutdown(socket.SHUT_RDWR)
                conn.close()
                continue
            conn.sendall("HELLO THERE".encode())

            info = conn.recv(self.buf_size).decode()
            info = json.loads(info)
            if not self._check_info(info):
                conn.shutdown(socket.SHUT_RDWR)
                conn.close()
                continue                

            conn = ChatSocket(conn,
                name=info["name"],
                room=None,
                event=self._event,
            )


    def _event(self, conn: ChatSocket):
        while True:
            try:
                ready_to_read, ready_to_write, in_error = select.select([conn.socket], [], [])
                if len(ready_to_read) > 0:
                    self._recv(conn)
            except select.error:
                conn.socket.shutdown(2)  # finish send & finish recv
                conn.socket.close()
                self._disconnect(conn)
                print("BYE")
                break
    
    def _recv(self, conn: ChatSocket):
        """This is for each connection's recv_thread, so don't call this directly.
        """
        data = conn.socket.recv(self.buf_size)
        if not data:
            print("WARNING: Data is empty ( = the socket has closed )")
            raise select.error

        data = data.decode()
        print(data)
        query = data.split()
        body_start = len(query[0]) + 1

        if conn.room is None:
            match query[0]:
                case "CREATE":  # CREATE room_name
                    room_name = data[body_start:]
                    room = Room(room_name)
                    room.add(conn)
                    self.rooms[room.name] = room

                case "JOIN":  # JOIN room_name
                    room_name = data[body_start:]
                    room = self.rooms.get(room_name)
                    if room is None:
                        print("Sorry, we couldn't find the corresponding room.")
                        return
                    if room.locked:
                        pass
                    else:
                        room.add(conn)

                case "ROOMLIST":  # ROOMLIST
                    room_list = []
                    for room_name, room in self.rooms.items():
                        room_list.append({
                            "RoomName": room_name,
                            "RoomDesc": room.description,
                            "Locked": room.locked,
                            "HeadCount": len(room.connections),
                            "MaxHeadCount": room.max_connections,
                        })
                    room_list_json = json.dumps(room_list, check_circular=False)
                    self.send([conn], f"ROOMLIST {room_list_json}")
                
                case "CHANGENAME":  # CHANGENAME new_name
                    new_name = data[body_start:]
                    conn.name = new_name
                    self.send([conn], f"CHANGENAME {conn.name}")

                case _:
                    print("Connection receive error")

        else:
            match query[0]:
                case "CHANGEROOM":  # CHANGEROOM NAME new_room_name / CHANGEROOM DESC new_room_desc
                    body_start += len(query[1]) + 1
                    if query[1] == "NAME":
                        new_room_name = data[body_start:]
                        self.rooms[new_room_name] = self.rooms.pop(conn.room.name)
                        conn.room.name = new_room_name
                    elif query[1] == "DESC":
                        conn.room.description = data[body_start:]
                    elif query[1] == "LOCK":
                        conn.room.locked = bool(query[2])

                case "CLICK":  # CLICK team x y
                    team = query[1]
                    x = int(query[2])
                    y = int(query[3])
                    self.send(conn.room.connections, f"CLICK {team} {x} {y}")

                case "PAUSE":  # PAUSE
                    pass


    def _disconnect(self, conn: ChatSocket):
        print(f"Connection \"{conn.name}\" DISCONNECTED")
        # 현재는 즉시 패배 처리하도록 했음
        if conn.room is not None:
            conn.room.remove(conn)
            self.send(conn.room.players, "RESULT win")


    @staticmethod
    def send(conns: list[ChatSocket], msg: str):
        for conn in conns:
            conn.socket.sendall(msg.encode())

    def _check_info(self, info: dict[str]) -> bool:
        if info["app"] == "LiveOmok" and info["ver"] == "0.1.0":
            return True
        return False



def main(args):
    import os
    rm = RoomManager(args)

    pid = os.getpid()
    th = threading.Thread(target=rm.run)
    th.start()
    input()
    os.kill(pid, 9)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="LiveOmok Server Program")
    parser.add_argument('--ip',
                        type=str, default='0.0.0.0', help='IP of this server program')
    parser.add_argument('--port', '-p',
                        type=int, default=5588, help='Port of this server program')
    parser.add_argument('--buf_size',
                        type=int, default=1024, help='Socket buffer size')
    parser.add_argument('--room_size',
                        type=int, default=2, help='Room size')
    args = parser.parse_args()
    main(args)
