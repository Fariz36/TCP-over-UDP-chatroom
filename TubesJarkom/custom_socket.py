import socket
import struct
import zlib

SYN = 0b0001
ACK = 0b0010
FIN = 0b0100

class BetterUDPSocket:
    def __init__(self, udp_socket=None):
        self.sock = udp_socket or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = None
        self.src_port = self.sock.getsockname()[1]
        self.dest_port = 0 
        self.seq = 0
        self.ack = 0
        self.connected = False

    def internet_checksum(data: bytes) -> int:
        if len(data) % 2 == 1:
            data += b'\x00'

        checksum = 0
        for i in range(0, len(data), 2):
            word = (data[i] << 8) + data[i + 1]
            checksum += word
            checksum = (checksum & 0xFFFF) + (checksum >> 16)

        return ~checksum & 0xFFFF

    def _make_packet(self, flags, seq, ack, data=b''):
        header = struct.pack('!BHHII', flags, self.src_port, self.dest_port, seq, ack)
        checksum = self.internet_checksum(header + data)
        return header + struct.pack('!H', checksum) + data 

    def _parse_packet(self, packet):
        header = packet[:13]
        checksum_recv = struct.unpack('!H', packet[13:15])[0]
        data = packet[15:]

        calc_checksum = self.internet_checksum(header + data)
        if checksum_recv != calc_checksum:
            raise ValueError("Checksum mismatch!")

        flags, src_port, dest_port, seq, ack = struct.unpack('!BHHII', header)
        return flags, src_port, dest_port, seq, ack, data

    def connect(self, ip_address, port):
        self.addr = (ip_address, port)
        self.dest_port = port
        self.seq = 100
        syn_packet = self._make_packet(SYN, self.seq, 0)
        self.sock.sendto(syn_packet, self.addr)

        while True:
            data, addr = self.sock.recvfrom(1024)
            flags, src_port, dest_port, seq, ack, _ = self._parse_packet(data)
            if flags & (SYN | ACK) and ack == self.seq + 1:
                self.ack = seq + 1
                self.dest_port = src_port  # update from peer
                break

        self.seq += 1
        ack_packet = self._make_packet(ACK, self.seq, self.ack)
        self.sock.sendto(ack_packet, self.addr)
        self.connected = True

    def listen(self):
        data, addr = self.sock.recvfrom(1024)
        flags, seq, ack, _ = self._parse_packet(data)
        if flags & SYN:
            self.addr = addr
            self.ack = seq + 1
            self.seq = 42  # server seq
            synack = self._make_packet(SYN | ACK, self.seq, self.ack)
            self.sock.sendto(synack, addr)

            data, addr = self.sock.recvfrom(1024)
            flags, seq2, ack2, _ = self._parse_packet(data)
            if flags & ACK and ack2 == self.seq + 1:
                self.connected = True

    def send(self, data):
        if not self.connected:
            raise RuntimeError("Not connected")
        pkt = self._make_packet(ACK, self.seq, self.ack, data)
        self.sock.sendto(pkt, self.addr)
        self.seq += len(data)

    def receive(self):
        while True:
            data, addr = self.sock.recvfrom(1024)
            flags, seq, ack, payload = self._parse_packet(data)
            if flags & FIN:
                self.response_close()
                return None
            if flags & ACK:
                self.ack = seq + len(payload)
                return payload
            
    # this thing sould initiate the closing connection
    # start by sending a FIN packet
    # then wait for ACK and FIN from the other side
    # finally send the final ACK
    def close(self):
        # Initiate active close (send FIN)
        fin_pkt = self._make_packet(FIN, self.seq, self.ack)
        self.sock.sendto(fin_pkt, self.addr)

        # Wait for ACK 
        # Wait for ACK or FIN|ACK
        while True:
            data, addr = self.sock.recvfrom(1024)
            flags, seq, ack, _ = self._parse_packet(data)

            if flags & ACK and ack == self.seq:
                if flags & FIN:
                    self.ack = seq + 1
                    ack_pkt = self._make_packet(ACK, self.seq, self.ack)
                    self.sock.sendto(ack_pkt, self.addr)
                    break
                else:
                    while True:
                        data, addr = self.sock.recvfrom(1024)
                        flags, seq, ack, _ = self._parse_packet(data)
                        if flags & FIN:
                            self.ack = seq + 1
                            ack_pkt = self._make_packet(ACK, self.seq, self.ack)
                            self.sock.sendto(ack_pkt, self.addr)
                            break
                    break
        
        # send the final ACK
        ack_pkt = self._make_packet(ACK, self.seq, self.ack)
        self.sock.sendto(ack_pkt, self.addr)

        print("[CLOSE] 4-way handshake complete")
        self.connected = False
        self.sock.close()

    def response_close(self):
        # Respond with FIN|ACK
        print("[RECEIVE] FIN : responding with FIN|ACK")
        fin_ack_pkt = self._make_packet(FIN | ACK, self.seq, self.ack)
        self.sock.sendto(fin_ack_pkt, self.addr)

        # Wait for final ACK
        while True:
            try:
                data, addr = self.sock.recvfrom(1024)
                flags, seq, ack, _ = self._parse_packet(data)
                if flags & ACK:
                    break
            except socket.timeout:
                print("[RECEIVE] Timeout waiting for final ACK")
                break

        print("[HANDLE_CLOSE] 4-way handshake complete")
        self.connected = False
        self.sock.close()
