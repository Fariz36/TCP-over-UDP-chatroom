from custom_socket import BetterUDPSocket
import time

def main():
    print("[CLIENT] Starting client...")
    sock = BetterUDPSocket()
    
    try:
        print("[CLIENT] Connecting to server...")
        sock.connect("127.0.0.1", 9000)
        print("[CLIENT] Connected successfully!")

        test_messages = [
            "Short msg",  # Small message (9 bytes)
            "This is a medium length message to test segmentation properly",  # Medium message (62 bytes)
            "This is a longer message that will definitely be split into multiple segments because it exceeds the maximum payload size of 64 bytes per segment and should demonstrate the Go-Back-N ARQ protocol working correctly.",  # Large message (192 bytes)
            "Final test"  # Small message (10 bytes)
        ]

        for i, msg in enumerate(test_messages, 1):
            print(f"\n[CLIENT] === Test {i}/{len(test_messages)} ===")
            print(f"[CLIENT] Message: '{msg}' ({len(msg)} bytes)")
            
            # send
            print("[CLIENT] Sending message...")
            start_time = time.time()
            try:
                sock.send(msg.encode())
                send_time = time.time() - start_time
                print(f"[CLIENT] Message sent successfully in {send_time:.3f} seconds")
            except Exception as e:
                print(f"[CLIENT] Error sending message: {e}")
                break
            
            # recv
            print("[CLIENT] Waiting for server response...")
            try:
                response = sock.receive()
                if response:
                    response_text = response.decode()
                    print(f"[CLIENT] Server response: '{response_text}' ({len(response)} bytes)")
                else:
                    print("[CLIENT] No response from server or connection closed")
                    break
            except Exception as e:
                print(f"[CLIENT] Error receiving response: {e}")
                break

            print(f"[CLIENT] Test {i} completed")
            time.sleep(1)

        print("\n[CLIENT] All tests completed")

    except Exception as e:
        print(f"[CLIENT] Error: {e}")
    
    finally:
        print("[CLIENT] Closing connection...")
        try:
            sock.close()
        except:
            pass
        print("[CLIENT] Client terminated")

if __name__ == "__main__":
    main()