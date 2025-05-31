from custom_socket import BetterUDPSocket
import time
from threading import Thread

class Server:
    def __init__(self, HOST, PORT):
        self.clients = []  # Changed from class variable to instance variable
        self.socket = BetterUDPSocket()
        self.socket.sock.bind((HOST, PORT))
        self.socket.listen()
        self.running = True
        print(f"[SERVER] Listening on {HOST}:{PORT}")

    def listen(self):
        print("[SERVER] Waiting for client connections...")
        
        connection_thread = Thread(target=self._handle_connections, daemon=True)
        connection_thread.start()
        
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[SERVER] Shutting down server...")
            self.running = False
    
    def _handle_connections(self):
        while self.running:
            try:
                client_sock, client_addr = self.socket.accept()
                print(f"[SERVER] Client connected from {client_addr}")
                
                Thread(target=self._complete_client_setup, args=(client_sock, client_addr)).start()
                
            except Exception as e:
                if self.running:  # Only log if we're still supposed to be running
                    print(f"[SERVER] Error accepting connection: {e}")
                    time.sleep(1)  # Brief pause before retrying
    
    def _complete_client_setup(self, client_sock, client_addr):
        try:
            start_time = time.time()
            client_name = None
            
            while time.time() - start_time < 10.0:  # 10 second timeout for username
                try:
                    username_data = client_sock.receive()
                    if username_data:
                        client_name = username_data.decode().strip()
                        break
                except:
                    time.sleep(0.1)
                    continue
            
            if not client_name:
                print(f"[SERVER] Client {client_addr} did not send a username within timeout. Closing connection.")
                client_sock.close()
                return

            print(f"[SERVER] Client {client_addr} registered as '{client_name}'")
            
            client = {
                'sock': client_sock,
                'addr': client_addr,
                'name': client_name
            }
            
            self.clients.append(client)
            
            welcome_msg = f"Welcome to the chat, {client_name}!"
            client_sock.send(welcome_msg.encode())
            
            self.broadcast_message("SERVER", f"{client_name} has joined the chat.")
            
            Thread(target=self.handle_client, args=(client,)).start()
            
        except Exception as e:
            print(f"[SERVER] Error in client setup for {client_addr}: {e}")
            try:
                client_sock.close()
            except:
                pass
    
    def handle_client(self, client):
        """Handle messages from a specific client"""
        client_name = client['name']
        client_sock = client['sock']
        
        try:
            while self.running:
                try:
                    raw_message = client_sock.receive()
                    
                    if raw_message is None:
                        continue
                    
                    client_message = raw_message.decode().strip()
                    
                    if not client_message:
                        print(f"[SERVER] Client {client_name} disconnected (empty message).")
                        break
                    
                    print(f"[SERVER] Message from {client_name}: {client_message}")
                    # Broadcast message to all clients except sender
                    self.broadcast_message(client_name, client_message)
                    
                except UnicodeDecodeError as e:
                    print(f"[SERVER] Failed to decode message from {client_name}: {e}")
                    continue
                except Exception as e:
                    print(f"[SERVER] Error receiving message from {client_name}: {e}")
                    break
                    
        except Exception as e:
            print(f"[SERVER] Error in handle_client for {client_name}: {e}")
        
        finally:
            self._cleanup_client(client)
    
    def _cleanup_client(self, client):
        client_name = client['name']
        
        print(f"[SERVER] Client {client_name} disconnected.")
        
        self.broadcast_message("SERVER", f"{client_name} has left the chat.")
        
        try:
            if client in self.clients:
                self.clients.remove(client)
        except ValueError:
            pass
        
        # Close client socket
        try:
            client['sock'].close()
        except:
            pass
    
    def broadcast_message(self, sender_name, message):
        clients_copy = self.clients.copy()
        
        for client in clients_copy:
            client_sock = client['sock']
            client_name = client['name']
            
            # Don't send message back to sender (unless it's a server message)
            if client_name != sender_name:
                try:
                    formatted_message = f"{sender_name}: {message}"
                    client_sock.send(formatted_message.encode())
                except Exception as e:
                    print(f"[SERVER] Failed to send message to {client_name}: {e}")
                    # Remove failed client
                    try:
                        if client in self.clients:
                            self.clients.remove(client)
                        client_sock.close()
                    except:
                        pass

if __name__ == "__main__":
    server = Server('127.0.0.1', 9000)
    server.listen()

# def handle_client(client_sock, client_addr):
#     print(f"[SERVER] Handling client {client_addr}")
    
#     try:
#         message_count = 1
#         while client_sock.connected:
#             print(f"[SERVER] Waiting for message #{message_count} from {client_addr}...")

#             msg = client_sock.receive()
#             if msg is None:
#                 print(f"[SERVER] No message received from {client_addr}")
#                 break
            
#             if len(msg) == 0:
#                 print(f"[SERVER] Empty message from {client_addr}")
#                 break
                
#             received_text = msg.decode()
#             print(f"[SERVER] Received message #{message_count}: '{received_text}' ({len(msg)} bytes)")
            
#             response = f"Server ACK #{message_count}: Received '{received_text}' ({len(msg)} bytes)"
#             print(f"[SERVER] Preparing response: '{response}' ({len(response)} bytes)")
            
#             try:
#                 start_time = time.time()
#                 client_sock.send(response.encode())
#                 send_time = time.time() - start_time
#                 print(f"[SERVER] Response #{message_count} sent in {send_time:.3f} seconds")
#             except Exception as e:
#                 print(f"[SERVER] Error sending response: {e}")
#                 break
            
#             message_count += 1
            
#             time.sleep(0.5)
            
#     except Exception as e:
#         print(f"[SERVER] Error handling client {client_addr}: {e}")
    
#     finally:
#         print(f"[SERVER] Closing connection with {client_addr}")
#         try:
#             client_sock.close()
#         except:
#             pass

# def main():
#     print("[SERVER] Starting server...")
#     server_addr = ("127.0.0.1", 9000)

#     client_count = 0
    
#     while True:
#         try:
#             client_count += 1
#             print(f"\n[SERVER] === Waiting for client #{client_count} ===")

#             sock = BetterUDPSocket()
#             sock.sock.bind(server_addr)
#             print(f"[SERVER] Listening on {server_addr[0]}:{server_addr[1]}")
            
#             print("[SERVER] Waiting for client connection...")
#             sock.listen()
            
#             client_addr = sock.addr
#             print(f"[SERVER] Client #{client_count} connected from {client_addr}")
            
#             handle_client(sock, client_addr)
            
#             print(f"[SERVER] Client #{client_count} session ended")
            
#         except KeyboardInterrupt:
#             print("\n[SERVER] Server shutting down...")
#             break
#         except Exception as e:
#             print(f"[SERVER] Error: {e}")
#             print("[SERVER] Restarting server...")
#             time.sleep(1)

# if __name__ == "__main__":
#     main()