import sys
import os
import json
import threading
import time
from datetime import datetime
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import pygame
from client import Client
from custom_socket import BetterUDPSocket
import socket # truly only for dns lookup 

# import os
# os.environ["SDL_AUDIODRIVER"] = "dummy"
# # import os
# # os.environ["SDL_AUDIODRIVER"] = "dummy"


class MusicPlayer(QObject):
    def __init__(self):
        super().__init__()
        pygame.mixer.init()
        self.current_song = None
        self.is_playing = False
        self.volume = 0.7
        
    def play_song(self, file_path):
        try:
            if os.path.exists(file_path):
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.set_volume(self.volume)
                pygame.mixer.music.play(-1)  # Loop indefinitely
                self.current_song = os.path.basename(file_path)
                self.is_playing = True
                return True
        except Exception as e:
            print(f"Error playing song: {e}")
        return False
        
    def stop_song(self):
        pygame.mixer.music.stop()
        self.is_playing = False
        self.current_song = None
        
    def set_volume(self, volume):
        self.volume = volume / 100.0
        pygame.mixer.music.set_volume(self.volume)

class ConnectionDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_style()
        self.username = ""
        self.ip_address = ""
        self.port = 0
        
    def setup_ui(self):
        self.setWindowTitle("~ ChatTCP ~")
        self.setFixedSize(400, 500)
        self.setModal(True)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("❤️ Connect to Server! ❤️")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            QLabel {
                color: #FF1493;
                font-size: 20px;
                font-weight: bold;
                font-family: 'Comic Sans MS', cursive;
                padding: 10px;
                border: none;
            }
        """)
        
        # Username input
        username_label = QLabel("Username:")
        username_label.setStyleSheet("color: #4A90E2; font-size: 14px; font-weight: bold; border: none;")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username...")
        
        # IP Address input
        ip_label = QLabel("IP Address:")
        ip_label.setStyleSheet("color: #4A90E2; font-size: 14px; font-weight: bold; border: none;")
        self.ip_input = QLineEdit()
        self.ip_input.setText("127.0.0.1")  # Default value
        self.ip_input.setPlaceholderText("Enter server IP address...")
        
        # Port input
        port_label = QLabel("Port:")
        port_label.setStyleSheet("color: #4A90E2; font-size: 14px; font-weight: bold; border: none;")
        self.port_input = QLineEdit()
        self.port_input.setText("9000")  # Default value
        self.port_input.setPlaceholderText("Enter server port...")
        
        # Buttons
        button_layout = QHBoxLayout()
        
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self.accept_connection)
        connect_btn.setFixedHeight(40)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setFixedHeight(40)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(connect_btn)
        
        # Add all widgets to layout
        layout.addWidget(title)
        layout.addSpacing(10)
        layout.addWidget(username_label)
        layout.addWidget(self.username_input)
        layout.addWidget(ip_label)
        layout.addWidget(self.ip_input)
        layout.addWidget(port_label)
        layout.addWidget(self.port_input)
        layout.addSpacing(20)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Set focus to username input
        self.username_input.setFocus()

    def setup_style(self):
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                          stop:0 #FFE4E6, stop:0.5 #E6F3FF, stop:1 #F0E6FF);
            }
            
            QLineEdit {
                padding: 8px 12px;
                font-size: 13px;
                border: 2px solid #FF69B4;
                border-radius: 15px;
                background: white;
                color: #2C2C2C;
                height: 20px;
            }
            
            QLineEdit:focus {
                border: 2px solid #FF1493;
                background: #FFF8F8;
            }
            
            QPushButton {
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
                border: 2px solid #4A90E2;
                border-radius: 15px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #E6F3FF, stop:1 #B6D7FF);
                color: #2C2C2C;
                min-width: 100px;
            }
            
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #CCE6FF, stop:1 #99CCFF);
                border: 2px solid #FF69B4;
            }
            
            QPushButton:pressed {
                background: #FFE4E6;
            }
        """)
        
    def accept_connection(self):
        username = self.username_input.text().strip()
        ip_address = self.ip_input.text().strip()
        port_text = self.port_input.text().strip()
        
        # Validate inputs
        if not username:
            QMessageBox.warning(self, "Invalid Input", "Please enter a username!")
            self.username_input.setFocus()
            return
            
        if not ip_address:
            QMessageBox.warning(self, "Invalid Input", "Please enter an IP address!")
            self.ip_input.setFocus()
            return
            
        try:
            port = int(port_text)
            if port < 1 or port > 65535:
                raise ValueError("Port out of range")
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid port number (1-65535)!")
            self.port_input.setFocus()
            return
        
        # Store the values
        self.username = username
        self.ip_address = ip_address
        self.port = port
        
        # Accept the dialog
        self.accept()

class ChatMessage(QWidget):
    def __init__(self, username, message, timestamp, is_own=False):
        super().__init__()
        self.setup_ui(username, message, timestamp, is_own)
        
    def setup_ui(self, username, message, timestamp, is_own):
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 5, 10, 5)
        
        # Message bubble
        bubble = QFrame()
        bubble.setMaximumWidth(400)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(12, 8, 12, 8)
        bubble_layout.setSpacing(2)
        
        # Username label
        username_label = QLabel(username)
        username_label.setStyleSheet("""
            QLabel {
                color: #FF69B4;
                font-weight: bold;
                font-size: 11px;
                background: transparent;
                border: none;
                padding-bottom: 10px;
            }
        """)
        
        # Message label
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet("""
            QLabel {
                color: #2C2C2C;
                font-size: 13px;
                line-height: 1.4;
                background: transparent;
                border: none;
                padding-bottom: 10px;
            }
        """)
        
        # Timestamp label
        time_label = QLabel(timestamp)
        time_label.setStyleSheet("""
            QLabel {
                color: #888;
                font-size: 9px;
                background: transparent;
                border: none;
            }
        """)
        
        bubble_layout.addWidget(username_label)
        bubble_layout.addWidget(message_label)
        bubble_layout.addWidget(time_label)
        
        # Style the bubble based on sender
        if is_own:
            bubble.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                              stop:0 #FFE4E6, stop:1 #FFB6C1);
                    border-radius: 15px;
                    border: 2px solid #FF69B4;
                }
            """)
            layout.addStretch()
            layout.addWidget(bubble)
        else:
            bubble.setStyleSheet("""
                QFrame {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                              stop:0 #E6F3FF, stop:1 #B6D7FF);
                    border-radius: 15px;
                    border: 2px solid #4A90E2;
                }
            """)
            layout.addWidget(bubble)
            layout.addStretch()
            
        self.setLayout(layout)

class KessokuChatRoom(QMainWindow):
    message_received = pyqtSignal(str, str, str, bool)
    
    def __init__(self, host, port):
        super().__init__()
        self.username = ""
        self.music_player = MusicPlayer()
        self.messages = []
        self.setup_ui()
        self.setup_style()
        self.socket = BetterUDPSocket()
        self.host = host
        self.port = port
        self.running = True
        self.message_received.connect(self.add_message)
        self.history_messages = []

    def setup_ui(self):
        self.setWindowTitle("ChatTCP")
        self.setGeometry(100, 100, 900, 700)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Content area (chat + music controls)
        content_layout = QHBoxLayout()
        
        # Chat area
        chat_widget = self.create_chat_area()
        content_layout.addWidget(chat_widget, 3)
        
        # Music control panel
        music_panel = self.create_music_panel()
        content_layout.addWidget(music_panel, 1)
        
        main_layout.addLayout(content_layout)
        
        # Input area
        input_widget = self.create_input_area()
        main_layout.addWidget(input_widget)
        
    def create_header(self):
        header = QFrame()
        header.setFixedHeight(80)
        header_layout = QHBoxLayout(header)
        
        # Title
        title = QLabel("❤️ Edbert Eddyson Gunawan ❤️")
        title.setStyleSheet("""
            QLabel {
                color: #FF1493;
                font-size: 24px;
                font-weight: bold;
                font-family: 'Comic Sans MS', cursive;
                border: none;
                padding: 10px;
            }
        """)
        title.setAlignment(Qt.AlignCenter)

        header_layout.addStretch()
        header_layout.addWidget(title)
        header_layout.addStretch()

        return header
    
    def send_heartbeat(self):
        while self.running:
            try:
                time.sleep(1)  # Send heartbeat every 1 second
                if self.running and hasattr(self, 'socket'):
                    # Send a special heartbeat message
                    self.socket.send("__HEARTBEAT__".encode())
            except Exception as e:
                if self.running:
                    print(f"[CLIENT] Heartbeat error: {e}")
                break       

    def create_chat_area(self):
        chat_frame = QFrame()
        chat_layout = QVBoxLayout(chat_frame)
        
        # Chat controls (refresh button)
        controls_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_chat_history)
        self.refresh_btn.setFixedWidth(150)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                padding: 6px 12px;
                font-size: 12px;
                font-weight: bold;
                border: 2px solid #32CD32;
                border-radius: 12px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #E6FFE6, stop:1 #B6FFB6);
                color: #2C2C2C;
            }
            
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #CCFFCC, stop:1 #99FF99);
                border: 2px solid #228B22;
            }
            
            QPushButton:pressed {
                background: #E6FFE6;
            }
        """)
        
        controls_layout.addWidget(self.refresh_btn)
        controls_layout.addStretch()
        
        chat_layout.addLayout(controls_layout)
        
        # Chat display
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.chat_widget = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.addStretch()
        
        self.chat_scroll.setWidget(self.chat_widget)
        chat_layout.addWidget(self.chat_scroll)
        
        return chat_frame
        
    def create_music_panel(self):
        music_frame = QFrame()
        music_frame.setMaximumWidth(250)
        music_layout = QVBoxLayout(music_frame)
        
        # Music panel title
        music_title = QLabel("🎵 Background Music 🎵")
        music_title.setAlignment(Qt.AlignCenter)
        music_title.setStyleSheet("""
            QLabel {
                color: #FF69B4;
                font-size: 16px;
                font-weight: bold;
                padding: 10px;
            }
        """)
        
        # Current song display
        self.current_song_label = QLabel("No song playing")
        self.current_song_label.setWordWrap(True)
        self.current_song_label.setAlignment(Qt.AlignCenter)
        self.current_song_label.setStyleSheet("""
            QLabel {
                color: #4A90E2;
                font-size: 12px;
                padding: 5px;
                background: rgba(255, 255, 255, 0.7);
                border-radius: 10px;
                border: 1px solid #FFB6C1;
            }
        """)
        
        # Music controls
        controls_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.select_and_play_song)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_music)
        
        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.stop_btn)
        
        # Volume control
        volume_layout = QHBoxLayout()
        volume_label = QLabel("Volume:")
        volume_label.setStyleSheet("color: #4A90E2; font-size: 12px; border: none;")
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_slider.valueChanged.connect(self.change_volume)
        
        volume_layout.addWidget(volume_label)
        volume_layout.addWidget(self.volume_slider)
               
        music_layout.addWidget(music_title)
        music_layout.addWidget(self.current_song_label)
        music_layout.addLayout(controls_layout)
        music_layout.addLayout(volume_layout)
        music_layout.addStretch()
        
        return music_frame
        
    def create_input_area(self):
        input_frame = QFrame()
        input_frame.setFixedHeight(100)
        input_layout = QHBoxLayout(input_frame)
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Type your message here... ")
        self.message_input.returnPressed.connect(self.send_message)
        
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self.send_message)
        send_btn.setFixedWidth(100)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(send_btn)
        
        return input_frame
        
    def setup_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                          stop:0 #FFE4E6, stop:0.5 #E6F3FF, stop:1 #F0E6FF);
            }
            
            QFrame {
                background: rgba(255, 255, 255, 0.8);
                border-radius: 15px;
                border: 2px solid #FFB6C1;
            }
            
            QLineEdit {
                padding: 10px;
                font-size: 14px;
                border: 2px solid #FF69B4;
                border-radius: 20px;
                background: white;
                color: #2C2C2C;
                height: 100px;
            }
            
            QLineEdit:focus {
                border: 2px solid #FF1493;
                background: #FFF8F8;
            }
            
            QPushButton {
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
                border: 2px solid #4A90E2;
                border-radius: 15px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #E6F3FF, stop:1 #B6D7FF);
                color: #2C2C2C;
            }
            
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #CCE6FF, stop:1 #99CCFF);
                border: 2px solid #FF69B4;
            }
            
            QPushButton:pressed {
                background: #FFE4E6;
            }
            
            QScrollArea {
                border: 2px solid #FFB6C1;
                border-radius: 15px;
                background: rgba(255, 255, 255, 0.9);
            }
            
            QSlider::groove:horizontal {
                border: 1px solid #999;
                height: 8px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #E6F3FF, stop:1 #B6D7FF);
                border-radius: 4px;
            }
            
            QSlider::handle:horizontal {
                background: #FF69B4;
                border: 2px solid #FF1493;
                width: 18px;
                border-radius: 9px;
                margin: -5px 0;
            }
        """)
        
    def send_message(self):
        message_text = self.message_input.text().strip()
        if message_text:
            # Handle rename command
            if message_text.startswith('!rename '):
                new_name = message_text.split(' ', 1)[1].strip()
                if new_name:
                    self.socket.send(message_text.encode())
                    # Don't add to chat history yet, wait for server confirmation
                else:
                    self.add_message("SYSTEM", "Invalid rename command. Usage: !rename <new_name>", 
                                datetime.now().strftime("%H:%M"), False)
            else:
                # Regular message
                timestamp = datetime.now().strftime("%H:%M")
                self.socket.send(message_text.encode())
                self.add_message(self.username, message_text, timestamp, is_own=True)
            
            self.message_input.clear()

    def add_message(self, username, message, timestamp, is_own=False):
        message_widget = ChatMessage(username, message, timestamp, is_own)
        self.history_messages.append((username, message, timestamp, is_own))
        if len(self.history_messages) > 20:
            self.history_messages.pop(0)
        
        # Remove stretch before adding new message
        if self.chat_layout.count() > 0:
            stretch_item = self.chat_layout.takeAt(self.chat_layout.count() - 1)
            
        self.chat_layout.addWidget(message_widget)
        self.chat_layout.addStretch()
        
        # Auto-scroll to bottom
        QTimer.singleShot(50, self.scroll_to_bottom)
        
    def scroll_to_bottom(self):
        scrollbar = self.chat_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def simulate_response(self, user_message):
        # Simple bot responses with band-themed replies
        responses = [
            "nigga1",
            "nigga2",
            "nigga3",
            "nigga4",
            "nigga5",
            "nigga6"
        ]
        
        import random
        response = random.choice(responses)
        
        # Delay the response to make it feel more natural
        self.add_message("ini lawan bicara", response, datetime.now().strftime("%H:%M"), is_own=False)
        
    def select_and_play_song(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Select Music File", 
            "", 
            "Audio Files (*.mp3 *.wav *.ogg *.m4a)"
        )
        
        if file_path:
            if self.music_player.play_song(file_path):
                self.current_song_label.setText(f"♪ {self.music_player.current_song} ♪")
            else:
                QMessageBox.warning(self, "Error", "Could not play the selected file!")
        
    def change_volume(self, value):
        self.music_player.set_volume(value)

    def stop_music(self):
        self.music_player.stop_song()
        self.current_song_label.setText("No song playing")
        
    def closeEvent(self, event):
        self.music_player.stop_song()
        pygame.mixer.quit()
        event.accept()
    
    
    def listen_for_messages(self):
        RETRIES = 5
        retry = 0
        while self.running:
            try:
                response = self.socket.receive()
                if response:
                    message = response.decode().strip()
                    
                    # Handle system messages and rename notifications
                    if message.startswith("SERVER:"):
                        # Extract the server message
                        server_msg = message[7:].strip()  # Remove "SERVER: " prefix
                        
                        # Check if this is a rename notification for this user
                        if " has changed their name to " in server_msg:
                            parts = server_msg.split(" has changed their name to ")
                            if len(parts) == 2:
                                old_name = parts[0].strip()
                                new_name = parts[1].strip().rstrip('.')
                                
                                # If this is our own rename
                                if old_name == self.username:
                                    self.handle_self_rename(new_name)
                        
                        # Display the server message
                        self.message_received.emit("SERVER", server_msg, datetime.now().strftime("%H:%M"), False)
                        
                    else:
                        # Handle regular user messages
                        if ":" in message:
                            sender, msg = message.split(":", 1)
                            sender = sender.strip()
                            msg = msg.strip()
                            
                            print(f"\n[{sender}] {msg}")
                            print(f"[{self.username}] ", end="", flush=True)
                            self.message_received.emit(sender, msg, datetime.now().strftime("%H:%M"), False)
                        else:
                            # Handle messages without proper format
                            print(f"\n[SYSTEM] {message}")
                            self.message_received.emit("SYSTEM", message, datetime.now().strftime("%H:%M"), False)
                else:
                    if self.running:
                        print("\n[CLIENT] Connection lost or server closed")
                        print("\n[CLIENT] Retrying")
                        retry += 1
                        if retry >= RETRIES:
                            self.running = False
                            break
            except Exception as e:
                if self.running:
                    print(f"\n[CLIENT] Error receiving message: {e}")
                    self.running = False
                break

    def handle_self_rename(self, new_username):
        """Handle renaming the user in the chat history."""
        old_username = self.username
        self.username = new_username
        
        # Update all messages in the chat history
        for i, (username, message, timestamp, is_own) in enumerate(self.history_messages):
            if username == old_username and is_own:
                self.history_messages[i] = (new_username, message, timestamp, is_own)
        
        print(f"[CLIENT] Renamed from {old_username} to {new_username}")
        
        # Refresh the chat to show updated names
        # self.refresh_chat_history()

    def start_socket(self, username):
        self.username = username

        try:
            self.socket.connect(self.host, self.port)
            print(f"[CLIENT] Connected to server at {self.host}:{self.port}")
                
            self.socket.send(username.encode())
            
            welcome_response = self.socket.receive()
            if welcome_response:
                self.add_message("SYSTEM", welcome_response.decode(), datetime.now().strftime("%H:%M"))
            
        except Exception as e:
            print(f"[CLIENT] Failed to connect: {e}")
            raise

        self.listenThread = threading.Thread(target=self.listen_for_messages, daemon=True)
        self.listenThread.start()

        
        self.heartbeatThread = threading.Thread(target=self.send_heartbeat, daemon=True)
        self.heartbeatThread.start()

    def refresh_chat_history(self):
        """Clear all current messages and reload only from history_messages"""
        # Clear all current chat widgets
        while self.chat_layout.count() > 0:
            child = self.chat_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Add stretch at the beginning
        self.chat_layout.addStretch()
        
        # Reload messages from history_messages
        for username, message, timestamp, is_own in self.history_messages:
            message_widget = ChatMessage(username, message, timestamp, is_own)
            
            # Remove stretch before adding new message
            if self.chat_layout.count() > 0:
                stretch_item = self.chat_layout.takeAt(self.chat_layout.count() - 1)
                
            self.chat_layout.addWidget(message_widget)
            self.chat_layout.addStretch()
        
        # Auto-scroll to bottom after refresh
        QTimer.singleShot(100, self.scroll_to_bottom)
        # print(f"[CLIENT] Chat refreshed - showing {len(self.history_messages)} messages from history")

def main():
    app = QApplication(sys.argv)

    # Custom font if available
    font_id = QFontDatabase.addApplicationFont("arial.ttf")
    if font_id != -1:
        font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
        app.setFont(QFont(font_family, 10))
    
    connection_dialog = ConnectionDialog()
    if connection_dialog.exec_() == QDialog.Accepted:
        # Get the connection details
        username = connection_dialog.username
        ip_address = connection_dialog.ip_address
        ip_address = socket.gethostbyname(ip_address)
        port = connection_dialog.port
        
        print(f"[CLIENT] Connecting to {ip_address}:{port} as {username}")
        
        

        # Create and show main window
        window = KessokuChatRoom(ip_address, port)
        window.show()
        window.start_socket(username)
        
        sys.exit(app.exec_())
    else:
        print("[CLIENT] Connection cancelled by user")
        sys.exit(0)
    
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()