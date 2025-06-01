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
        title = QLabel("Edbert Eddyson Gunawan")
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
        
    def create_chat_area(self):
        chat_frame = QFrame()
        chat_layout = QVBoxLayout(chat_frame)
        
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
            timestamp = datetime.now().strftime("%H:%M")
            self.socket.send(message_text.encode())
            self.add_message(self.username, message_text, timestamp, is_own=True)
            self.message_input.clear()

    def add_message(self, username, message, timestamp, is_own=False):
        message_widget = ChatMessage(username, message, timestamp, is_own)
        
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
                    sender, msg = message.split(maxsplit=1)
                    if message:
                        print(f"\n[{sender[:-1]}] {msg}")
                        print(f"[{self.username}] ", end="", flush=True)  # Restore input prompt
                        self.message_received.emit(sender[:-1], msg, datetime.now().strftime("%H:%M"), False)
                else:
                    if self.running:  # Only print if we're still supposed to be running
                        print("\n[CLIENT] Connection lost or server closed")
                        print("\n[CLIENT] Retrying")
                        if retry >= RETRIES:
                            self.running = False
                            break
            except Exception as e:
                if self.running:
                    print(f"\n[CLIENT] Error receiving message: {e}")
                    self.running = False
                break

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

def main():
    username = str(input("input username: "))
    app = QApplication(sys.argv)

    # Custom font if available
    font_id = QFontDatabase.addApplicationFont("arial.ttf")
    if font_id != -1:
        font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
        app.setFont(QFont(font_family, 10))
    
    window = KessokuChatRoom("127.0.0.1", 9000)
    window.show()
    window.start_socket(username)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()