import socket
import struct
import time
import threading
from queue import Queue, Empty
from typing import List, Optional, Dict, Tuple
import random

SYN = 0b0001
ACK = 0b0010
FIN = 0b0100
TERM = 0b1000
TIMEOUT = 1.0
RETRIES = 5
WINDOW_SIZE = 4
MAX_SEGMENT_SIZE = 128
HEADER_SIZE = 17  # 1+2+2+4+4+2+2 bytes
MAX_PAYLOAD_SIZE = MAX_SEGMENT_SIZE - HEADER_SIZE  # 111 bytes
SEGMENT_TIMEOUT = 2.0
CRC16_POLYNOMIAL = 0xA001  # CRC-16-CCITT polynomial

class Segment:
    def __init__(self, flags: int, src_port: int, dest_port: int, seq: int, ack: int, data: bytes = b''):
        self.flags = flags
        self.src_port = src_port
        self.dest_port = dest_port
        self.seq = seq
        self.ack = ack
        self.data = data[:MAX_PAYLOAD_SIZE]
        self.checksum = self._calculate_checksum()
        self.crc16 = self._calculate_crc16()
    
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
    
    def _calculate_crc16(self) -> int:
        crc = 0xFFFF
        for byte in self.data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ CRC16_POLYNOMIAL
                else:
                    crc >>= 1
        return crc & 0xFFFF
    
    def pack(self) -> bytes:
        header = struct.pack('!BHHIIHH', self.flags, self.src_port, self.dest_port, 
                           self.seq, self.ack, self.checksum, self.crc16)
        segment = header + self.data
        
        if len(segment) > MAX_SEGMENT_SIZE:
            raise ValueError(f"Segment size {len(segment)} exceeds maximum {MAX_SEGMENT_SIZE}")
        
        return segment
    
    @classmethod
    def unpack(cls, data: bytes):
        if len(data) < HEADER_SIZE:
            raise ValueError("Packet too short")
        
        if len(data) > MAX_SEGMENT_SIZE:
            raise ValueError(f"Segment size {len(data)} exceeds maximum {MAX_SEGMENT_SIZE}")
        
        header = data[:HEADER_SIZE]
        payload = data[HEADER_SIZE:]
        flags, src_port, dest_port, seq, ack, checksum, crc16 = struct.unpack('!BHHIIHH', header)
        
        segment = cls(flags, src_port, dest_port, seq, ack, payload)
        if segment.checksum != checksum:
            raise ValueError("Checksum mismatch")
        
        if segment.crc16 != crc16:
            raise ValueError("CRC16 mismatch")
        
        return segment
    
    def is_termination(self) -> bool:
        return bool(self.flags & TERM)
    
    def set_termination(self):
        self.flags |= TERM
        self.checksum = self._calculate_checksum()

class BetterUDPClientSocket:    
    def __init__(self, server_sock, client_addr, server_port, client_port, seq_num, ack_num):
        self.server_sock = server_sock
        self.addr = client_addr
        self.server_port = server_port
        self.client_port = client_port
        self.seq_num = seq_num
        self.ack_num = ack_num
        self.connected = True
        
        # Go-Back-N variables
        self.Sb = seq_num
        self.Sm = self.Sb + WINDOW_SIZE - 1
        self.next_to_send = self.Sb
        self.Rn = ack_num
        
        # Buffers and synchronization
        self.send_buffer = {}
        self.ack_received = threading.Event()
        self.latest_ack = self.Sb
        self.ack_lock = threading.Lock()
        
        # Message handling
        self.message_queue = Queue()
        self.message_segments = {}
        self.receive_lock = threading.Lock()
        
        # Control flags
        self.sending_complete = False
        self.send_lock = threading.Lock()
        
    
    def send(self, data: bytes):
        if not self.connected:
            raise RuntimeError("Not connected")
        return self._send_go_back_n_pipelined(data)
    
    def receive(self) -> Optional[bytes]:
        if not self.connected:
            raise RuntimeError("Not connected")
        
        try:
            message = self.message_queue.get(timeout=10.0)
            print(f"[CLIENT_SOCK {self.addr}] Received message ({len(message)} bytes)")
            return message
        except Empty:
            return None
    
    def close(self):
        if not self.connected:
            return
        
        print(f"[CLIENT_SOCK {self.addr}] Closing connection")
        fin_segment = Segment(FIN, self.server_port, self.client_port, self.seq_num, 0)
        
        for attempt in range(RETRIES):
            self.server_sock.sendto(fin_segment.pack(), self.addr)
            print(f"[CLIENT_SOCK {self.addr}] Sent FIN")
            time.sleep(0.1)
        
        self.connected = False
    
    def _send_go_back_n_pipelined(self, data: bytes):
        
        segments = self._prepare_segments(data)
        if not segments:
            return False
        
        base_seq = self.next_to_send
        total_segments = len(segments)
        
        with self.send_lock:
            self.Sb = base_seq
            self.next_to_send = base_seq
            self.latest_ack = base_seq
            self.sending_complete = False
        
        segment_timestamps = {}
        
        while self.Sb < base_seq + total_segments:
            while (self.next_to_send < self.Sb + WINDOW_SIZE and 
                   self.next_to_send < base_seq + total_segments):
                
                seq = self.next_to_send
                if seq in self.send_buffer:
                    segment = self.send_buffer[seq]
                    self.server_sock.sendto(segment.pack(), self.addr)
                    segment_timestamps[seq] = time.time()
                    
                    with self.send_lock:
                        self.next_to_send += 1
            
            self._check_and_slide_window()
            
            # Check for timeouts
            current_time = time.time()
            for seq in range(self.Sb, min(self.Sb + WINDOW_SIZE, self.next_to_send)):
                if seq in segment_timestamps:
                    if current_time - segment_timestamps[seq] > SEGMENT_TIMEOUT:
                        self._retransmit_window(segment_timestamps)
                        break
            
            time.sleep(0.001)
        
        print(f"[CLIENT_SOCK {self.addr}] Send complete")
        return True
    
    def _prepare_segments(self, data: bytes):
        segments = []
        offset = 0
        seq = self.next_to_send
        
        while offset < len(data):
            chunk = data[offset:offset + MAX_PAYLOAD_SIZE]
            segment = Segment(0, self.server_port, self.client_port, seq, 0, chunk)
            
            if offset + len(chunk) >= len(data):
                segment.set_termination()
            
            segments.append((seq, segment))
            self.send_buffer[seq] = segment
            offset += MAX_PAYLOAD_SIZE
            seq += 1
        
        return segments
    
    def _check_and_slide_window(self):
        with self.ack_lock:
            if self.latest_ack > self.Sb:
                old_sb = self.Sb
                
                for s in range(self.Sb, self.latest_ack):
                    if s in self.send_buffer:
                        del self.send_buffer[s]
                
                self.Sb = self.latest_ack
                return True
        return False
    
    def _retransmit_window(self, segment_timestamps):
        print(f"[CLIENT_SOCK {self.addr}] Retransmitting window from {self.Sb}")
        
        with self.send_lock:
            self.next_to_send = self.Sb
        
        current_time = time.time()
        for seq in range(self.Sb, min(self.Sb + WINDOW_SIZE, self.next_to_send + WINDOW_SIZE)):
            if seq in self.send_buffer:
                segment = self.send_buffer[seq]
                self.server_sock.sendto(segment.pack(), self.addr)
                segment_timestamps[seq] = current_time
    
    def handle_received_segment(self, segment):
        print(f"[CLIENT_SOCK {self.addr}] Handling segment: flags={bin(segment.flags)}, seq={segment.seq}, ack={segment.ack}")
        
        # Handle ACK
        if (segment.flags & ACK) and not (segment.flags & (SYN | FIN)) and segment.ack > 0:
            self._handle_ack_segment(segment)
        
        # Handle data
        if len(segment.data) > 0 and not (segment.flags & (SYN | FIN)):
            self._handle_data_segment(segment)
        
        # Handle FIN
        if segment.flags & FIN:
            self._handle_fin_segment(segment)
    
    def _handle_ack_segment(self, segment):
        with self.ack_lock:
            if segment.ack > self.latest_ack:
                self.latest_ack = segment.ack
                self.ack_received.set()
    
    def _handle_data_segment(self, segment):
        with self.receive_lock:
            if segment.seq == self.Rn:
                print(f"[CLIENT_SOCK {self.addr}] Accepting segment {segment.seq}")
                self.message_segments[segment.seq] = segment.data
                self.Rn += 1
                
                if segment.is_termination():
                    complete_message = self._assemble_message()
                    if complete_message:
                        self.message_queue.put(complete_message)
                        self.message_segments.clear()
            
            self._send_ack(self.Rn)
    
    def _handle_fin_segment(self, segment):
        print(f"[CLIENT_SOCK {self.addr}] Received FIN")
        fin_ack = Segment(FIN | ACK, self.server_port, self.client_port, 
                         self.seq_num, segment.seq + 1)
        self.server_sock.sendto(fin_ack.pack(), self.addr)
        self.connected = False
    
    def _assemble_message(self):
        if not self.message_segments:
            return None
        
        seq_numbers = sorted(self.message_segments.keys())
        message_parts = [self.message_segments[seq] for seq in seq_numbers]
        return b''.join(message_parts)
    
    def _send_ack(self, ack_num):
        ack_segment = Segment(ACK, self.server_port, self.client_port, 0, ack_num)
        self.server_sock.sendto(ack_segment.pack(), self.addr)

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
        self.seq_num = random.randint(1000, 9999)
        self.ack_num = 0
        self.connected = False
        
        # For server mode - multiple clients
        self.clients: Dict[Tuple[str, int], BetterUDPClientSocket] = {}
        self.clients_lock = threading.RLock()
        self.server_mode = False
        self.running = False
        self.receiver_thread = None
        self.connection_queue = Queue()
        
        # Original single-client variables (for client mode)
        self.Sb = 0
        self.Sm = 0
        self.N = WINDOW_SIZE
        self.next_to_send = 0
        self.Rn = 0
        self.send_buffer = {}
        self.ack_received = threading.Event()
        self.latest_ack = 0
        self.ack_lock = threading.Lock()
        self.message_queue = Queue()
        self.message_segments = {}
        self.receive_lock = threading.Lock()
        self.sending_complete = False
        self.send_lock = threading.Lock()
    
    def listen(self):
        self.server_mode = True
        self._update_src_port()
        self._start_receiver_thread()
        
        print(f"[SERVER] Listening on port {self.src_port}")
    
    def accept(self):
        if not self.server_mode:
            raise RuntimeError("Socket not in server mode. Call listen() first.")
        
        try:
            client_sock = self.connection_queue.get(timeout=30.0)
            return client_sock, client_sock.addr
        except Empty:
            raise TimeoutError("No incoming connections")
    
    def _start_receiver_thread(self):
        if not self.running:
            self.running = True
            self.receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True)
            self.receiver_thread.start()
    
    def _receiver_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(MAX_SEGMENT_SIZE)  # Use optimized size
                
                try:
                    segment = Segment.unpack(data)
                    
                    if self.server_mode:
                        self._handle_server_segment(segment, addr)
                    else:
                        self._handle_client_segment(segment, addr)
                        
                except ValueError as e:
                    print(f"[RECV] Bad packet from {addr}: {e}")
                    continue
                    
            except socket.timeout:
                continue
            except OSError:
                break
    
    def _handle_server_segment(self, segment, addr):
        # Handle new connection (SYN)
        if segment.flags & SYN and not (segment.flags & ACK):
            self._handle_new_connection(segment, addr)
            return
        
        # Handle existing client
        with self.clients_lock:
            if addr in self.clients:
                client_sock = self.clients[addr]
                client_sock.handle_received_segment(segment)
            else:
                print(f"[SERVER] Received segment from unknown client {addr}")
    
    def _handle_new_connection(self, segment, addr):
        print(f"[SERVER] New connection from {addr}")
        
        # Send SYN-ACK
        server_seq = random.randint(1000, 9999)
        ack_num = segment.seq + 1
        
        synack_segment = Segment(SYN | ACK, self.src_port, segment.src_port, 
                               server_seq, ack_num)
        self.sock.sendto(synack_segment.pack(), addr)
        print(f"[SERVER] Sent SYN-ACK to {addr}")
        
        # Wait for final ACK
        start_time = time.time()
        while time.time() - start_time < TIMEOUT * 2:
            try:
                data, client_addr = self.sock.recvfrom(MAX_SEGMENT_SIZE)
                if client_addr == addr:
                    try:
                        ack_segment = Segment.unpack(data)
                        if (ack_segment.flags & ACK) and ack_segment.ack == server_seq + 1:
                            # Connection established
                            client_sock = BetterUDPClientSocket(
                                self.sock, addr, self.src_port, segment.src_port,
                                server_seq + 1, ack_segment.seq
                            )
                            
                            with self.clients_lock:
                                self.clients[addr] = client_sock
                            
                            self.connection_queue.put(client_sock)
                            print(f"[SERVER] Client {addr} connected successfully")
                            return
                    except ValueError:
                        continue
            except socket.timeout:
                continue
        
        print(f"[SERVER] Failed to complete handshake with {addr}")
    
    def _handle_client_segment(self, segment, addr):
        if addr == self.addr:
            print(f"[CLIENT] Received segment: flags={bin(segment.flags)}, seq={segment.seq}, ack={segment.ack}")
            
            if (segment.flags & ACK) and not (segment.flags & (SYN | FIN)) and segment.ack > 0:
                self._handle_ack_segment(segment)
            
            if len(segment.data) > 0 and not (segment.flags & (SYN | FIN)):
                self._handle_data_segment(segment)
    
    def connect(self, ip_address: str, port: int):
        self.addr = (ip_address, port)
        self.dest_port = port
        self._update_src_port()
        
        # 3-way handshake
        syn_segment = Segment(SYN, self.src_port, self.dest_port, self.seq_num, 0)
        
        for attempt in range(RETRIES):
            self.sock.sendto(syn_segment.pack(), self.addr)
            print(f"[CLIENT] Sent SYN (seq={self.seq_num})")
            
            try:
                start_time = time.time()
                while time.time() - start_time < TIMEOUT:
                    try:
                        data, addr = self.sock.recvfrom(MAX_SEGMENT_SIZE)
                        if addr == self.addr:
                            segment = Segment.unpack(data)
                            if (segment.flags & (SYN | ACK)) == (SYN | ACK) and segment.ack == self.seq_num + 1:
                                # Send final ACK
                                self.ack_num = segment.seq + 1
                                self.seq_num += 1
                                ack_segment = Segment(ACK, self.src_port, self.dest_port, 
                                                    self.seq_num, self.ack_num)
                                self.sock.sendto(ack_segment.pack(), self.addr)
                                print(f"[CLIENT] Connected to {self.addr}")
                                
                                # Initialize Go-Back-N
                                self.connected = True
                                self.Sb = self.seq_num
                                self.Sm = self.Sb + self.N - 1
                                self.next_to_send = self.Sb
                                self.Rn = self.ack_num
                                
                                self._start_receiver_thread()
                                return
                    except (ValueError, socket.timeout):
                        continue
            except socket.timeout:
                continue
        
        raise TimeoutError("Connection failed")
    
    def _update_src_port(self):
        try:
            if self.src_port == 0:
                self.src_port = self.sock.getsockname()[1]
        except (OSError, socket.error):
            pass
    
    def send(self, data: bytes):
        if not self.connected:
            raise RuntimeError("Not connected")
        return self._send_go_back_n_pipelined(data)
    
    def receive(self) -> Optional[bytes]:
        if not self.connected:
            raise RuntimeError("Not connected")
        
        try:
            message = self.message_queue.get(timeout=10.0)
            return message
        except Empty:
            return None
    
    def close(self):
        if self.server_mode:
            self._close_server()
        else:
            self._close_client()
    
    def _close_server(self):
        self.running = False
        
        with self.clients_lock:
            for client_sock in list(self.clients.values()):
                client_sock.close()
            self.clients.clear()
        
        if self.receiver_thread:
            self.receiver_thread.join(timeout=1)
        
        self.sock.close()
    
    def _close_client(self):
        if not self.connected:
            return
        
        self.running = False
        fin_segment = Segment(FIN, self.src_port, self.dest_port, self.seq_num, 0)
        
        for attempt in range(RETRIES):
            self.sock.sendto(fin_segment.pack(), self.addr)
            time.sleep(0.1)
        
        self.connected = False
        if self.receiver_thread:
            self.receiver_thread.join(timeout=1)
        
        self.sock.close()
    
    def _send_go_back_n_pipelined(self, data: bytes):
        segments = self._prepare_segments(data)
        if not segments:
            return False
        
        base_seq = self.next_to_send
        total_segments = len(segments)
        
        with self.send_lock:
            self.Sb = base_seq
            self.next_to_send = base_seq
            self.latest_ack = base_seq
            self.sending_complete = False
        
        segment_timestamps = {}
        
        while self.Sb < base_seq + total_segments:
            while (self.next_to_send < self.Sb + self.N and 
                   self.next_to_send < base_seq + total_segments):
                
                seq = self.next_to_send
                if seq in self.send_buffer:
                    segment = self.send_buffer[seq]
                    self.sock.sendto(segment.pack(), self.addr)
                    segment_timestamps[seq] = time.time()
                    
                    with self.send_lock:
                        self.next_to_send += 1
            
            if self._check_and_slide_window():
                continue
            
            current_time = time.time()
            for seq in range(self.Sb, min(self.Sb + self.N, self.next_to_send)):
                if seq in segment_timestamps:
                    if current_time - segment_timestamps[seq] > SEGMENT_TIMEOUT:
                        self._retransmit_window(segment_timestamps)
                        break
            
            time.sleep(0.001)
        
        self.sending_complete = True
        return True
    
    def _prepare_segments(self, data: bytes):
        segments = []
        offset = 0
        seq = self.next_to_send
        
        while offset < len(data):
            chunk = data[offset:offset + MAX_PAYLOAD_SIZE]
            segment = Segment(0, self.src_port, self.dest_port, seq, 0, chunk)
            
            if offset + len(chunk) >= len(data):
                segment.set_termination()
            
            segments.append((seq, segment))
            self.send_buffer[seq] = segment
            offset += MAX_PAYLOAD_SIZE
            seq += 1
        
        return segments
    
    def _check_and_slide_window(self):
        with self.ack_lock:
            if self.latest_ack > self.Sb:
                old_sb = self.Sb
                
                for s in range(self.Sb, self.latest_ack):
                    if s in self.send_buffer:
                        del self.send_buffer[s]
                
                self.Sb = self.latest_ack
                return True
        return False
    
    def _retransmit_window(self, segment_timestamps):
        with self.send_lock:
            self.next_to_send = self.Sb
        
        current_time = time.time()
        for seq in range(self.Sb, min(self.Sb + self.N, self.next_to_send + self.N)):
            if seq in self.send_buffer:
                segment = self.send_buffer[seq]
                self.sock.sendto(segment.pack(), self.addr)
                segment_timestamps[seq] = current_time
    
    def _handle_ack_segment(self, segment):
        with self.ack_lock:
            if segment.ack > self.latest_ack:
                self.latest_ack = segment.ack
                self.ack_received.set()
    
    def _handle_data_segment(self, segment):
        with self.receive_lock:
            if segment.seq == self.Rn:
                self.message_segments[segment.seq] = segment.data
                self.Rn += 1
                
                if segment.is_termination():
                    complete_message = self._assemble_message()
                    if complete_message:
                        self.message_queue.put(complete_message)
                        self.message_segments.clear()
            
            self._send_ack(self.Rn)
    
    def _assemble_message(self):
        if not self.message_segments:
            return None
        
        seq_numbers = sorted(self.message_segments.keys())
        message_parts = [self.message_segments[seq] for seq in seq_numbers]
        return b''.join(message_parts)
    
    def _send_ack(self, ack_num):
        ack_segment = Segment(ACK, self.src_port, self.dest_port, 0, ack_num)
        self.sock.sendto(ack_segment.pack(), self.addr)