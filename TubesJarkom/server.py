# server.py
from custom_socket import BetterUDPSocket

def main():
    print("[SERVER] Starting...")
    while True:
        sock = BetterUDPSocket()
        sock.sock.bind(("127.0.0.1", 9000))
        print("[SERVER] Waiting for connection...")
        sock.listen()
        print("[SERVER] Connection established!")

        while True:
            try:
                msg = sock.receive()
                print("[SERVER] Received:", msg.decode())
                sock.send(b"Message received!")
            except:
                break

if __name__ == "__main__":
    main()
