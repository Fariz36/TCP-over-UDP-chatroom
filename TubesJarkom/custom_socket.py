import socket
import struct

SYN = 0b0001
ACK = 0b0010
FIN = 0b0100

class BetterUDPSocket:
    def __init__(self, udp_socket=None):
        self.sock = udp_socket or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addr = None
        self.seq = 0
        self.ack = 0
        self.connected = False

    def _make_packet(self, flags, seq, ack, data=b''):
        return struct.pack('!BII', flags, seq, ack) + data

    def _parse_packet(self, packet):
        flags, seq, ack = struct.unpack('!BII', packet[:9])
        data = packet[9:]
        return flags, seq, ack, data

    def connect(self, ip_address, port):
        self.addr = (ip_address, port)
        self.seq = 100  # random start
        syn_packet = self._make_packet(SYN, self.seq, 0)
        self.sock.sendto(syn_packet, self.addr)

        while True:
            data, addr = self.sock.recvfrom(1024)
            flags, seq, ack, _ = self._parse_packet(data)
            if flags & (SYN | ACK) and ack == self.seq + 1:
                self.ack = seq + 1
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
        self.connected = False
        self.sock.close()

        print("[HANDLE_CLOSE] 4-way handshake complete")

