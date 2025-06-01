from custom_socket import BetterUDPSocket
import threading
import sys
import time


class Client:
    def __init__(self, HOST, PORT):
        self.socket = BetterUDPSocket()
        self.host = HOST
        self.port = PORT
        self.name = ""
        self.running = True
        
        try:
            self.socket.connect(HOST, PORT)
            print(f"[CLIENT] Connected to server at {HOST}:{PORT}")
            
            # Get username from user
            self.name = input("[CLIENT] Enter your username: ").strip()
            if not self.name:
                self.name = "Anonymous"
                
            self.socket.send(self.name.encode())
            
            welcome_response = self.socket.receive()
            if welcome_response:
                print(f"[CLIENT] {welcome_response.decode()}")
            
            print(f"[CLIENT] You are now connected as '{self.name}'")
            print("[CLIENT] Type your messages or 'exit' to quit")
            
        except Exception as e:
            print(f"[CLIENT] Failed to connect: {e}")
            raise

    def listen_for_messages(self):
        while self.running:
            try:
                response = self.socket.receive()
                if response:
                    message = response.decode().strip()
                    sender, msg = message.split(maxsplit=1)
                    if message:
                        print(f"\n[{sender[:-1]}] {msg}")
                        print(f"[{self.name}] ", end="", flush=True)  # Restore input prompt
                else:
                    if self.running:  # Only print if we're still supposed to be running
                        print("\n[CLIENT] Connection lost or server closed")
                        self.running = False
                        break
            except Exception as e:
                if self.running:
                    print(f"\n[CLIENT] Error receiving message: {e}")
                    self.running = False
                break

    def send_messages(self):
        while self.running:
            try:
                message = input(f"[{self.name}] ").strip()
                
                if not self.running:
                    break
                    
                if message.lower() == 'exit':
                    print("[CLIENT] Exiting...")
                    self.running = False
                    break
                
                if message:  # Only send non-empty messages
                    self.socket.send(message.encode())
                    
            except KeyboardInterrupt:
                print("\n[CLIENT] Interrupted. Exiting...")
                self.running = False
                break
            except Exception as e:
                print(f"[CLIENT] Error sending message: {e}")
                self.running = False
                break

    def heartbeat(self):
        while self.running:
            try:
                time.sleep(1)  # Send heartbeat every 1 second
                if self.running:
                    # Send a simple heartbeat message that won't be broadcast
                    heartbeat_message = "__HEARTBEAT__"
                    self.socket.send(heartbeat_message.encode())
            except Exception as e:
                if self.running:
                    print(f"[CLIENT] Error sending heartbeat: {e}")
                    self.running = False
                break

    def start_chat(self):
        try:
            listen_thread = threading.Thread(target=self.listen_for_messages, daemon=True)
            listen_thread.start()
            
            heartbeat_thread = threading.Thread(target=self.heartbeat, daemon=True)
            heartbeat_thread.start()
            
            self.send_messages()
            
        except Exception as e:
            print(f"[CLIENT] Error in chat: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        self.running = False
        try:
            self.socket.close()
            print("[CLIENT] Connection closed")
        except Exception as e:
            print(f"[CLIENT] Error closing connection: {e}")

if __name__ == "__main__":
    try:
        client = Client('127.0.0.1', 9000)
        client.start_chat()
    except Exception as e:
        print(f"[CLIENT] Failed to start client: {e}")