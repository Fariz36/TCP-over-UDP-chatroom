import socket
import struct
import time
import threading
from queue import Queue, Empty
from typing import List, Optional
import random

# Constants
SYN = 0b0001
ACK = 0b0010
FIN = 0b0100
TIMEOUT = 1.0
RETRIES = 5
WINDOW_SIZE = 4  # N = window size
MAX_PAYLOAD_SIZE = 64  # Maximum payload per segment
SEGMENT_TIMEOUT = 2.0  # Timeout for individual segments

class Segment:
    def __init__(self, flags: int, src_port: int, dest_port: int, seq: int, ack: int, data: bytes = b''):
        self.flags = flags
        self.src_port = src_port
        self.dest_port = dest_port
        self.seq = seq
        self.ack = ack
        self.data = data[:MAX_PAYLOAD_SIZE]
        self.checksum = self._calculate_checksum()
    
    def _calculate_checksum(self) -> int:
        header = struct.pack('!BHHII', self.flags, self.src_port, self.dest_port, self.seq, self.ack)
        packet_data = header + self.data
        
        if len(packet_data) % 2 == 1:
            packet_data += b'\x00'
        
        checksum = 0
        for i in range(0, len(packet_data), 2):
            word = (packet_data[i] << 8) + packet_data[i + 1]
            checksum += word
            checksum = (checksum & 0xFFFF) + (checksum >> 16)
        
        return ~checksum & 0xFFFF
    
    def pack(self) -> bytes:
        header = struct.pack('!BHHIIH', self.flags, self.src_port, self.dest_port, 
                           self.seq, self.ack, self.checksum)
        return header + self.data
    
    @classmethod
    def unpack(cls, data: bytes):
        if len(data) < 15:
            raise ValueError("Packet too short")
        
        header = data[:15]
        payload = data[15:]
        flags, src_port, dest_port, seq, ack, checksum = struct.unpack('!BHHIIH', header)
        
        segment = cls(flags, src_port, dest_port, seq, ack, payload)
        if segment.checksum != checksum:
            raise ValueError("Checksum mismatch")
        
        return segment

class BetterUDPSocket:
    def __init__(self, udp_socket=None):
        self.sock = udp_socket or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.1)
        self.addr = None
        
        try:
            self.src_port = self.sock.getsockname()[1]
        except (OSError, socket.error):
            self.src_port = 0
            
        self.dest_port = 0
        self.seq_num = random.randint(1000, 9999)  # Random initial sequence
        self.ack_num = 0
        self.connected = False
        
        # Go-Back-N var : send
        self.Sb = 0  # sequence base
        self.Sm = 0  # sequence max
        self.N = WINDOW_SIZE  # window size
        self.next_to_send = 0
        
        # Go-Back-N var: recv
        self.Rn = 0
        
        # Buffers and synchronization
        self.send_buffer = {}  # Buffer for segments to be sent/resent
        self.ack_received = threading.Event()
        self.latest_ack = 0
        self.ack_lock = threading.Lock()
        
        # Message handling with queue approach
        self.message_queue = Queue()  # Queue for complete messages
        self.message_segments = {}    # Buffer for assembling messages
        self.receive_lock = threading.Lock()
        
        # Threading
        self.running = False
        self.receiver_thread = None
        
        # Sending control
        self.sending_complete = False
        self.send_lock = threading.Lock()
    
    def _update_src_port(self):
        try:
            if self.src_port == 0:
                self.src_port = self.sock.getsockname()[1]
        except (OSError, socket.error):
            pass
        
    def _start_receiver_thread(self):
        if not self.running:
            self.running = True
            self.receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
            self.receiver_thread.start()
    
    def _receiver_loop(self):
        while self.running and self.connected:
            try:
                data, addr = self.sock.recvfrom(128)
                if addr == self.addr:
                    try:
                        segment = Segment.unpack(data)
                        self._handle_received_segment(segment)
                    except ValueError as e:
                        print(f"[RECV] Bad packet from {addr}: {e}")
                        continue
            except socket.timeout:
                continue
            except OSError:
                break
    
    def _handle_received_segment(self, segment):
        print(f"[RECV] Segment: flags={bin(segment.flags)}, seq={segment.seq}, ack={segment.ack}, data_len={len(segment.data)}")
        
        # Handle ACK (for our sent data)
        if (segment.flags & ACK) and not (segment.flags & (SYN | FIN)) and segment.ack > 0:
            self._handle_ack_segment(segment)
        
        # Handle data segment (incoming data for us)
        if len(segment.data) > 0 and not (segment.flags & (SYN | FIN)):
            self._handle_data_segment(segment)
    

    def _handle_ack_segment(self, segment):
        with self.ack_lock:
            if segment.ack > self.latest_ack:
                old_ack = self.latest_ack
                self.latest_ack = segment.ack
                print(f"[ACK] Received ACK {segment.ack} (was {old_ack})")
                self.ack_received.set()
    

    def _handle_data_segment(self, segment):
        print(f"[DATA] Received seq={segment.seq}, expecting Rn={self.Rn}")
        
        with self.receive_lock:
            if segment.seq == self.Rn:

                # Accept packet - in order
                print(f"[DATA] Accepting segment {segment.seq}")
                self.message_segments[segment.seq] = segment.data
                self.Rn += 1
                
                # Check if this is the last segment (smaller than max payload)
                if len(segment.data) < MAX_PAYLOAD_SIZE:
                    print(f"[DATA] End of message detected (segment size: {len(segment.data)})")
                    complete_message = self._assemble_message()
                    if complete_message:
                        self.message_queue.put(complete_message)
                        print(f"[DATA] Complete message queued ({len(complete_message)} bytes)")
                        self.message_segments.clear()  # Clear for next message
            else:
                print(f"[DATA] Out of order segment {segment.seq}, expecting {self.Rn}")
            
            # Always send ACK for expected sequence number
            self._send_ack(self.Rn)
    

    def _assemble_message(self):
        if not self.message_segments:
            return None
        
        # Sort segments by sequence number and assemble
        seq_numbers = sorted(self.message_segments.keys())
        message_parts = []
        
        for seq in seq_numbers:
            message_parts.append(self.message_segments[seq])
            print(f"[ASSEMBLE] Adding segment {seq} ({len(self.message_segments[seq])} bytes)")
        
        return b''.join(message_parts)
    
    def _send_ack(self, ack_num):
        ack_segment = Segment(ACK, self.src_port, self.dest_port, 0, ack_num)
        self.sock.sendto(ack_segment.pack(), self.addr)
        print(f"[ACK] Sent ACK for {ack_num}")
    

    def _slide_window(self):
        with self.ack_lock:
            if self.latest_ack > self.Sb:
                old_sb = self.Sb
                
                # Remove acknowledged segments
                for s in range(self.Sb, self.latest_ack):
                    if s in self.send_buffer:
                        del self.send_buffer[s]
                
                self.Sb = self.latest_ack
                print(f"[WINDOW] Slid from {old_sb} to {self.Sb}")
                return True
        return False
    
    def connect(self, ip_address: str, port: int):
        self.addr = (ip_address, port)
        self.dest_port = port
        self._update_src_port()  # Update src_port after any potential binding
        
        # Step 1: Send SYN
        syn_segment = Segment(SYN, self.src_port, self.dest_port, self.seq_num, 0)
        
        for attempt in range(RETRIES):
            self.sock.sendto(syn_segment.pack(), self.addr)
            print(f"[HANDSHAKE] Sent SYN (seq={self.seq_num})")
            
            try:
                start_time = time.time()
                while time.time() - start_time < TIMEOUT:
                    try:
                        data, addr = self.sock.recvfrom(128)
                        if addr == self.addr:
                            segment = Segment.unpack(data)
                            if (segment.flags & (SYN | ACK)) == (SYN | ACK) and segment.ack == self.seq_num + 1:
                                # Step 3: Send ACK
                                self.ack_num = segment.seq + 1
                                self.seq_num += 1
                                ack_segment = Segment(ACK, self.src_port, self.dest_port, 
                                                    self.seq_num, self.ack_num)
                                self.sock.sendto(ack_segment.pack(), self.addr)
                                print(f"[HANDSHAKE] Sent ACK (seq={self.seq_num}, ack={self.ack_num})")
                                
                                # Initialize Go-Back-N variables
                                self.connected = True
                                self.Sb = self.seq_num
                                self.Sm = self.Sb + self.N - 1
                                self.next_to_send = self.Sb
                                self.Rn = self.ack_num  # Start expecting from server's next seq
                                
                                print(f"[CONNECT] Initialized - Sb={self.Sb}, Sm={self.Sm}, Rn={self.Rn}")
                                
                                self._start_receiver_thread()
                                return
                    except (ValueError, socket.timeout):
                        continue
            except socket.timeout:
                continue
        
        raise TimeoutError("Connection handshake failed")
    
    def listen(self):
        # Make sure src_port is updated after binding
        self._update_src_port()
        
        while True:
            try:
                data, addr = self.sock.recvfrom(128)
                segment = Segment.unpack(data)
                
                if segment.flags & SYN and not (segment.flags & ACK):
                    self.addr = addr
                    self.dest_port = segment.src_port
                    
                    # Step 2: Send SYN-ACK
                    self.ack_num = segment.seq + 1
                    synack_segment = Segment(SYN | ACK, self.src_port, self.dest_port,
                                           self.seq_num, self.ack_num)
                    self.sock.sendto(synack_segment.pack(), addr)
                    print(f"[HANDSHAKE] Sent SYN-ACK (seq={self.seq_num}, ack={self.ack_num})")
                    
                    # Wait for final ACK
                    start_time = time.time()
                    while time.time() - start_time < TIMEOUT * 2:
                        try:
                            data, addr = self.sock.recvfrom(128)
                            if addr == self.addr:
                                ack_segment = Segment.unpack(data)
                                if (ack_segment.flags & ACK) and ack_segment.ack == self.seq_num + 1:
                                    print(f"[HANDSHAKE] Received ACK (seq={ack_segment.seq}, ack={ack_segment.ack})")
                                    
                                    # Initialize Go-Back-N variables
                                    self.connected = True
                                    self.seq_num += 1
                                    self.Sb = self.seq_num
                                    self.Sm = self.Sb + self.N - 1
                                    self.next_to_send = self.Sb
                                    self.Rn = ack_segment.seq  # Start expecting from client's next seq
                                    
                                    print(f"[LISTEN] Initialized - Sb={self.Sb}, Sm={self.Sm}, Rn={self.Rn}")
                                    
                                    self._start_receiver_thread()
                                    return
                        except (ValueError, socket.timeout):
                            continue
            except (socket.timeout, ValueError):
                continue
    
    def send(self, data: bytes):
        if not self.connected:
            raise RuntimeError("Not connected")
        
        return self._send_go_back_n_pipelined(data)
    
    def _send_go_back_n_pipelined(self, data: bytes):
        print(f"[SEND] Starting pipelined Go-Back-N send, data size: {len(data)} bytes")
        
        # Prepare segments
        segments = self._prepare_segments(data)
        if not segments:
            return False
        
        base_seq = self.next_to_send
        total_segments = len(segments)
        
        print(f"[SEND] Created {total_segments} segments (seq {base_seq} to {base_seq + total_segments - 1})")
        
        # Initialize sending state
        with self.send_lock:
            self.Sb = base_seq
            self.next_to_send = base_seq
            self.latest_ack = base_seq  # Reset latest_ack
            self.sending_complete = False
        
        # Timestamps for timeout management
        segment_timestamps = {}
        
        # MAIN PIPELINED LOOP - TRUE GO-BACK-N
        print("[SEND] Starting continuous pipeline loop...")
        while self.Sb < base_seq + total_segments:
            
            # 1. CONTINUOUS SENDING - Send segments as window allows
            while (self.next_to_send < self.Sb + self.N and 
                   self.next_to_send < base_seq + total_segments):
                
                seq = self.next_to_send
                if seq in self.send_buffer:
                    segment = self.send_buffer[seq]
                    self.sock.sendto(segment.pack(), self.addr)
                    segment_timestamps[seq] = time.time()
                    print(f"[PIPELINE] Sent segment {seq} (window: {self.Sb}-{self.Sb + self.N - 1})")
                    
                    with self.send_lock:
                        self.next_to_send += 1
                else:
                    break
            
            # 2. CHECK FOR ACKs and SLIDE WINDOW (non-blocking)
            if self._check_and_slide_window():
                # Window slid, continue sending more segments
                continue
            
            # 3. CHECK FOR TIMEOUTS and RETRANSMIT if needed
            current_time = time.time()
            for seq in range(self.Sb, min(self.Sb + self.N, self.next_to_send)):
                if seq in segment_timestamps:
                    if current_time - segment_timestamps[seq] > SEGMENT_TIMEOUT:
                        print(f"[TIMEOUT] Segment {seq} timed out, retransmitting window from {self.Sb}")
                        self._retransmit_window(segment_timestamps)
                        break
            
            # Small delay to prevent busy waiting
            time.sleep(0.001)
        
        print("[SEND] All segments sent and acknowledged successfully!")
        self.sending_complete = True
        return True
    
    def _check_and_slide_window(self):
        with self.ack_lock:
            if self.latest_ack > self.Sb:
                # Slide window
                old_sb = self.Sb
                
                # Remove acknowledged segments
                for s in range(self.Sb, self.latest_ack):
                    if s in self.send_buffer:
                        del self.send_buffer[s]
                
                self.Sb = self.latest_ack
                print(f"[WINDOW] Slid from {old_sb} to {self.Sb} (ACK received)")
                return True
        return False
    
    def _retransmit_window(self, segment_timestamps):
        print(f"[RETX] Retransmitting window from Sb={self.Sb}")
        
        # Reset next_to_send to base
        with self.send_lock:
            self.next_to_send = self.Sb
        
        # Retransmit all segments in current window
        current_time = time.time()
        for seq in range(self.Sb, min(self.Sb + self.N, self.next_to_send + self.N)):
            if seq in self.send_buffer:
                segment = self.send_buffer[seq]
                self.sock.sendto(segment.pack(), self.addr)
                segment_timestamps[seq] = current_time
                print(f"[RETX] Retransmitted segment {seq}")
    
    def _prepare_segments(self, data: bytes):
        segments = []
        offset = 0
        seq = self.next_to_send
        
        while offset < len(data):
            chunk = data[offset:offset + MAX_PAYLOAD_SIZE]
            segment = Segment(0, self.src_port, self.dest_port, seq, 0, chunk)  # No flags for data
            segments.append((seq, segment))
            self.send_buffer[seq] = segment
            offset += MAX_PAYLOAD_SIZE
            seq += 1
        
        return segments
    
    def receive(self) -> Optional[bytes]:
        if not self.connected:
            raise RuntimeError("Not connected")
        
        return self._receive_go_back_n()
    
    def _receive_go_back_n(self) -> Optional[bytes]:
        print("[RECEIVE] Waiting for data...")
        
        try:
            # Try to get message from queue with timeout
            message = self.message_queue.get(timeout=10.0)
            print(f"[RECEIVE] Got message from queue ({len(message)} bytes)")
            return message
        except Empty:
            print("[RECEIVE] Timeout - no message in queue")
            
            # Check if we have partial data being assembled
            with self.receive_lock:
                if self.message_segments:
                    print(f"[RECEIVE] Has partial data: {len(self.message_segments)} segments")
                else:
                    print("[RECEIVE] No data at all")
            
            return None
    
    def close(self):
        if not self.connected:
            return
        
        self._perform_connection_teardown()
    
    def _perform_connection_teardown(self):
        print("[CLOSE] Initiating connection termination")
        self.running = False
        
        # Send FIN
        fin_segment = Segment(FIN, self.src_port, self.dest_port, self.seq_num, 0)
        
        for attempt in range(RETRIES):
            self.sock.sendto(fin_segment.pack(), self.addr)
            print(f"[CLOSE] Sent FIN (seq={self.seq_num})")
            
            try:
                start_time = time.time()
                while time.time() - start_time < TIMEOUT:
                    try:
                        data, addr = self.sock.recvfrom(128)
                        if addr == self.addr:
                            segment = Segment.unpack(data)
                            
                            if segment.flags & (FIN | ACK):
                                # Send final ACK
                                ack_segment = Segment(ACK, self.src_port, self.dest_port,
                                                    self.seq_num + 1, segment.seq + 1)
                                self.sock.sendto(ack_segment.pack(), self.addr)
                                print("[CLOSE] Sent final ACK")
                                break
                    except ValueError:
                        continue
                break
            except socket.timeout:
                continue
        
        # Cleanup
        self._cleanup_resources()
    
    def _cleanup_resources(self):
        self.connected = False
        
        if self.receiver_thread and self.receiver_thread.is_alive():
            self.receiver_thread.join(timeout=1)
        
        self.sock.close()
        print("[CLOSE] Connection terminated")