from custom_socket import BetterUDPSocket
import time
from threading import Thread, Lock

class Server:
    def __init__(self, HOST, PORT):
        self.clients = []  # Changed from class variable to instance variable
        self.clients_lock = Lock() 
        self.socket = BetterUDPSocket()
        self.socket.sock.bind((HOST, PORT))
        self.socket.listen()
        self.running = True
        print(f"[SERVER] Listening on {HOST}:{PORT}")

    def listen(self):
        print("[SERVER] Waiting for client connections...")
        
        connection_thread = Thread(target=self._handle_connections, daemon=True)
        connection_thread.start()
        
        heartbeat_thread = Thread(target=self._monitor_heartbeat, daemon=True)
        heartbeat_thread.start()
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
                if self.running:  
                    print(f"[SERVER] Error accepting connection: {e}")
                    time.sleep(1)  
    
    def _complete_client_setup(self, client_sock, client_addr):
        try:
            start_time = time.time()
            client_name = None
            
            while time.time() - start_time < 10.0:
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
                'name': client_name,
                'last_heartbeat': time.time(),  
                'being_kicked': False  
            }
            
            with self.clients_lock:
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
            while self.running and not client.get('being_kicked', False):
                try:
                    raw_message = client_sock.receive()
                    
                    if raw_message is None:
                        continue
                    
                    if client.get('being_kicked', False):
                        break
                    
                    client_message = raw_message.decode().strip()
                    
                    if not client_message:
                        print(f"[SERVER] Client {client_name} disconnected (empty message).")
                        break
                    
                    client['last_heartbeat'] = time.time()
                    
                    if client_message == "__HEARTBEAT__":
                        print(f"[SERVER] Received heartbeat from {client_name}")
                        continue

                    if client_message.startswith('!disconnect'):
                        print(f"[SERVER] Client {client_name} requested to disconnect.")
                        client['being_kicked'] = True
                        self._cleanup_client(client)
                        break
                    if client_message.startswith('!rename'):
                        new_name = client_message.split(' ', 1)[1].strip()
                        if new_name:
                            with self.clients_lock:
                                for c in self.clients:
                                    if c['name'] == new_name and c != client:
                                        client_sock.send(f"Username '{new_name}' is already taken.".encode())
                                        continue
                                client['name'] = new_name
                            print(f"[SERVER] Client {client_name} changed name to {new_name}.")
                            self.broadcast_message("SERVER", f"{client_name} has changed their name to {new_name}.")
                            for client_new in self.clients:
                                if client_new['sock'] == client_sock:
                                    client_new['name'] = new_name
                            client_name = new_name
                        else:
                            client_sock.send("Invalid rename command. Usage: !rename <new_name>".encode())
                        continue
                    if client_message.startswith('!kill'):
                        password = client_message.split(' ', 1)[1].strip() if ' ' in client_message else ''
                        if password == 'wazeazure':
                            print("[SERVER] Server shutdown requested via !kill command.")
                            self.running = False
                            self.broadcast_message("SERVER", "Server is shutting down.")
                            client_sock.send("Server is shutting down.".encode())
                            break
                        else:
                            continue

                    with self.clients_lock:
                        if client not in self.clients or client.get('being_kicked', False):
                            break
                    
                    print(f"[SERVER] Message from {client_name}: {client_message}")
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
            if client.get('being_kicked', False):
                self._cleanup_client(client)
    
    def _cleanup_client(self, client):
        client_name = client['name']
        print(f"[SERVER] Client {client_name} disconnected.")
        
        broadcast_thread = Thread(
            target=self.broadcast_message, 
            args=("SERVER", f"{client_name} has left the chat."),
            daemon=True
        )
        broadcast_thread.start()
        
        with self.clients_lock:
            try:
                if client in self.clients:
                    self.clients.remove(client)
            except ValueError:
                pass
        
        try:
            client['sock'].close()
        except:
            pass
    
    def broadcast_message(self, sender_name, message):
        with self.clients_lock:
            clients_copy = self.clients.copy()
        
        for client in clients_copy:
            if client.get('being_kicked', False):
                continue
            
            if client['name'] == sender_name and sender_name != "SERVER":
                continue
            
            try:
                formatted_message = f"{sender_name}: {message}"
                client['sock'].send(formatted_message.encode())
            except Exception as e:
                # Only log the error, don't remove the client here
                print(f"[SERVER] Failed to send to {client['name']}: {e}")
    def _monitor_heartbeat(self):
        while self.running:
            try:
                current_time = time.time()
                clients_to_remove = []
                
                with self.clients_lock:
                    clients_copy = self.clients.copy() 
                
                for client in clients_copy:
                    if client.get('being_kicked', False):
                        continue
                        
                    last_heartbeat = client.get('last_heartbeat', current_time)
                    if current_time - last_heartbeat > 30.0:
                        print(f"[SERVER] {client['name']} timed out (no heartbeat for {current_time - last_heartbeat:.1f}s)")
                        self.broadcast_message("SERVER", f"{client['name']} menghilang dari Tubes, {client['name']} tercallout di X!")
                        clients_to_remove.append(client)
                
                for client in clients_to_remove:
                    self._cleanup_client(client)
                
                time.sleep(1)
            except Exception as e:
                print(f"[SERVER] Error in heartbeat monitor: {e}")

if __name__ == "__main__":
    server = Server('127.0.0.1', 9000)
    server.listen()