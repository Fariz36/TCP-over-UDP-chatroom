# client.py
from custom_socket import BetterUDPSocket
import time

def main():
    print("[CLIENT] Connecting...")
    sock = BetterUDPSocket()
    sock.connect("127.0.0.1", 9000)

    print("[CLIENT] Connected to server.")

    messages = ["Hello", "How are you?"]
    for msg in messages:
        print(f"[CLIENT] Sending: {msg}")
        sock.send(msg.encode())
        response = sock.receive()
        print("[CLIENT] Received:", response.decode())
        time.sleep(1)
    print("[CLIENT] Disconnecting...")
    sock.close()

if __name__ == "__main__":
    main()
###