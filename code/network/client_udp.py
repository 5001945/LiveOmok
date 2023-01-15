# UDP p2p: https://www.youtube.com/watch?v=IbzGL_tjmv4
import socket
import sys
import os.path
import threading


def connect_server(server_list='server_list.txt'):
    # find server list
    rendezvous = None
    server_list_file = os.path.join(os.path.dirname(__file__), server_list)  # LiveOmok/network/server_list.txt
    with open(server_list_file, 'r') as f:
        lines = f.readlines()
        for line in lines:
            line = line.split('#')[0].strip()  # ignore comments
            if line:
                rendezvous = (line, 5588)
    if rendezvous is None:
        raise FileNotFoundError(server_list + " is empty.")

    # connect to rendezvous server
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
    sock.bind(('0.0.0.0', 56456))
    sock.sendto(b'0', rendezvous)

    while True:
        data = sock.recv(1024).decode()
        if data.strip() == 'ready':
            print('checked in with server, waiting')
            break
    data = sock.recv(1024).decode()
    ip, sport, dport = data.split(' ')  # ip, source port, dest port
    sport = int(sport)
    dport = int(dport)
    sock.close()

    # punch hole
    # equiv: echo 'punch hole' | nc -u -p 50001 x.x.x.x 50002
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', sport))
    sock.sendto(b'0', (ip, dport))
    sock.close()

    print('ready to exchange messages\n')

    return ip, sport, dport


class OmokUDP:
    def __init__(self) -> None:
        self.ip, self.sport, self.dport = connect_server()

        self.rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx.bind(('0.0.0.0', self.sport))
        self.tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tx.bind(('0.0.0.0', self.dport))

        self.rx_event = lambda data: print(f"peer: {data.decode()}")

    def start_listen(self):
        # start new thread
        self.listener = threading.Thread(target=self._listen, daemon=True)
        self.listener.start()

    def _listen(self):
        while True:
            data = self.rx.recv(1024)
            self.rx_event(data.decode())

    def send(self, msg: str):
        self.tx.sendto(msg.encode(), (self.ip, self.sport))
