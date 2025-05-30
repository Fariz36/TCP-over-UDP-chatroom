from custom_socket import BetterUDPSocket
import time
#import threading

def handle_client(client_sock, client_addr):
    print(f"[SERVER] Handling client {client_addr}")
    
    try:
        message_count = 1
        while client_sock.connected:
            print(f"[SERVER] Waiting for message #{message_count} from {client_addr}...")

            msg = client_sock.receive()
            if msg is None:
                print(f"[SERVER] No message received from {client_addr}")
                break
            
            if len(msg) == 0:
                print(f"[SERVER] Empty message from {client_addr}")
                break
                
            received_text = msg.decode()
            print(f"[SERVER] Received message #{message_count}: '{received_text}' ({len(msg)} bytes)")
            
            response = f"Server ACK #{message_count}: Received '{received_text}' ({len(msg)} bytes)"
            print(f"[SERVER] Preparing response: '{response}' ({len(response)} bytes)")
            
            try:
                start_time = time.time()
                client_sock.send(response.encode())
                send_time = time.time() - start_time
                print(f"[SERVER] Response #{message_count} sent in {send_time:.3f} seconds")
            except Exception as e:
                print(f"[SERVER] Error sending response: {e}")
                break
            
            message_count += 1
            
            time.sleep(0.5)
            
    except Exception as e:
        print(f"[SERVER] Error handling client {client_addr}: {e}")
    
    finally:
        print(f"[SERVER] Closing connection with {client_addr}")
        try:
            client_sock.close()
        except:
            pass

def main():
    print("[SERVER] Starting server...")
    server_addr = ("127.0.0.1", 9000)

    client_count = 0
    
    while True:
        try:
            client_count += 1
            print(f"\n[SERVER] === Waiting for client #{client_count} ===")

            sock = BetterUDPSocket()
            sock.sock.bind(server_addr)
            print(f"[SERVER] Listening on {server_addr[0]}:{server_addr[1]}")
            
            print("[SERVER] Waiting for client connection...")
            sock.listen()
            
            client_addr = sock.addr
            print(f"[SERVER] Client #{client_count} connected from {client_addr}")
            
            handle_client(sock, client_addr)
            
            print(f"[SERVER] Client #{client_count} session ended")
            
        except KeyboardInterrupt:
            print("\n[SERVER] Server shutting down...")
            break
        except Exception as e:
            print(f"[SERVER] Error: {e}")
            print("[SERVER] Restarting server...")
            time.sleep(1)

if __name__ == "__main__":
    main()