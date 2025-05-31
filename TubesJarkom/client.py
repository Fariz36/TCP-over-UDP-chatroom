from custom_socket import BetterUDPSocket
import threading
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
                    if message:
                        print(f"\n{message}")
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

    def start_chat(self):
        try:
            listen_thread = threading.Thread(target=self.listen_for_messages, daemon=True)
            listen_thread.start()
            
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

# def main():
#     print("[CLIENT] Starting client...")
#     sock = BetterUDPSocket()
    
#     try:
#         print("[CLIENT] Connecting to server...")
#         sock.connect("127.0.0.1", 9000)
#         print("[CLIENT] Connected successfully!")

#         test_messages = [
#             "Short msg",  # Small message (9 bytes)
#             "This is a medium length message to test segmentation properly",  # Medium message (62 bytes)
#             "This is a longer message that will definitely be split into multiple segments because it exceeds the maximum payload size of 64 bytes per segment and should demonstrate the Go-Back-N ARQ protocol working correctly.",  # Large message (192 bytes)
#             "Final test"  # Small message (10 bytes)
#         ]

#         for i, msg in enumerate(test_messages, 1):
#             print(f"\n[CLIENT] === Test {i}/{len(test_messages)} ===")
#             print(f"[CLIENT] Message: '{msg}' ({len(msg)} bytes)")
            
#             # send
#             print("[CLIENT] Sending message...")
#             start_time = time.time()
#             try:
#                 sock.send(msg.encode())
#                 send_time = time.time() - start_time
#                 print(f"[CLIENT] Message sent successfully in {send_time:.3f} seconds")
#             except Exception as e:
#                 print(f"[CLIENT] Error sending message: {e}")
#                 break
            
#             # recv
#             print("[CLIENT] Waiting for server response...")
#             try:
#                 response = sock.receive()
#                 if response:
#                     response_text = response.decode()
#                     print(f"[CLIENT] Server response: '{response_text}' ({len(response)} bytes)")
#                 else:
#                     print("[CLIENT] No response from server or connection closed")
#                     break
#             except Exception as e:
#                 print(f"[CLIENT] Error receiving response: {e}")
#                 break

#             print(f"[CLIENT] Test {i} completed")
#             time.sleep(1)

#         print("\n[CLIENT] All tests completed")

#     except Exception as e:
#         print(f"[CLIENT] Error: {e}")
    
#     finally:
#         print("[CLIENT] Closing connection...")
#         try:
#             sock.close()
#         except:
#             pass
#         print("[CLIENT] Client terminated")

# if __name__ == "__main__":
#     main()