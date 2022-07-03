# UDP p2p: https://www.youtube.com/watch?v=IbzGL_tjmv4
import socket

known_port = 5598

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
sock.bind(('0.0.0.0', 5588))

while True:
    clients = []

    while True:
        if len(clients) == 0:
            print("Waiting for new client...")
        else:
            print("Waiting for another client...")

        data, address = sock.recvfrom(128)

        print(f"- Connection from: {address}")
        clients.append(address)

        sock.sendto(b'ready', address)

        if len(clients) == 2:
            print("- Got 2 clients, sending details to each\n")
            break

    c1 = clients.pop()
    c1_addr, c1_port = c1
    c2 = clients.pop()
    c2_addr, c2_port = c2

    sock.sendto('{} {} {}'.format(c1_addr, c1_port, known_port).encode(), c2)
    sock.sendto('{} {} {}'.format(c2_addr, c2_port, known_port).encode(), c1)
