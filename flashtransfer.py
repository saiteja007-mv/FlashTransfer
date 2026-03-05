#!/usr/bin/env python3
"""
FlashTransfer - Fast Cross-Platform File Transfer
GUI application for transferring large files between Linux and Windows
With Auto-Discovery - devices on same network auto-detect each other
"""

import sys
import socket
import os
import json
import hashlib
import threading
import struct
from pathlib import Path
from datetime import datetime

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QProgressBar, QFileDialog, QLineEdit,
        QTextEdit, QGroupBox, QSpinBox, QMessageBox, QSplitter,
        QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
        QSystemTrayIcon, QMenu, QListWidget, QListWidgetItem
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtGui import QIcon, QFont, QPalette, QColor
except ImportError:
    print("Installing PyQt6...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyQt6", "-q"])
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QProgressBar, QFileDialog, QLineEdit,
        QTextEdit, QGroupBox, QSpinBox, QMessageBox, QSplitter,
        QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
        QSystemTrayIcon, QMenu, QListWidget, QListWidgetItem
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt6.QtGui import QIcon, QFont, QPalette, QColor


CHUNK_SIZE = 8192  # 8KB chunks for optimal large file transfer
DEFAULT_PORT = 55432
DISCOVERY_PORT = 55433
BROADCAST_ADDR = '<broadcast>'
DISCOVERY_INTERVAL = 3  # seconds


class DiscoveryThread(QThread):
    """Background thread for device discovery"""
    device_found = pyqtSignal(str, str, str)  # ip, hostname, platform
    device_lost = pyqtSignal(str)  # ip
    log = pyqtSignal(str)
    
    def __init__(self, port=DISCOVERY_PORT):
        super().__init__()
        self.port = port
        self.running = True
        self.devices = {}  # ip -> last_seen
        self.own_ip = self._get_own_ip()
        
    def _get_own_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def run(self):
        # Start listener thread
        listener = threading.Thread(target=self._listen_for_beacons, daemon=True)
        listener.start()
        
        # Start broadcaster thread
        broadcaster = threading.Thread(target=self._broadcast_beacon, daemon=True)
        broadcaster.start()
        
        # Monitor device timeouts
        while self.running:
            current_time = datetime.now().timestamp()
            timeout_ips = []
            
            for ip, last_seen in self.devices.items():
                if current_time - last_seen > 10:  # 10 second timeout
                    timeout_ips.append(ip)
            
            for ip in timeout_ips:
                del self.devices[ip]
                self.device_lost.emit(ip)
            
            self.msleep(1000)  # Check every second
    
    def _listen_for_beacons(self):
        """Listen for discovery beacons from other devices"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        try:
            sock.bind(('', self.port))
        except:
            self.log.emit(f"Discovery port {self.port} in use")
            return
        
        sock.settimeout(1)
        
        while self.running:
            try:
                data, addr = sock.recvfrom(1024)
                ip = addr[0]
                
                # Ignore self
                if ip == self.own_ip:
                    continue
                
                try:
                    beacon = json.loads(data.decode())
                    if beacon.get('app') == 'FlashTransfer':
                        self.devices[ip] = datetime.now().timestamp()
                        self.device_found.emit(
                            ip,
                            beacon.get('hostname', 'Unknown'),
                            beacon.get('platform', 'Unknown')
                        )
                except:
                    pass
            except socket.timeout:
                continue
            except:
                break
        
        sock.close()
    
    def _broadcast_beacon(self):
        """Broadcast discovery beacon"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)
        
        beacon = {
            'app': 'FlashTransfer',
            'hostname': socket.gethostname(),
            'platform': sys.platform,
            'port': DEFAULT_PORT,
            'timestamp': datetime.now().isoformat()
        }
        
        beacon_data = json.dumps(beacon).encode()
        
        while self.running:
            try:
                sock.sendto(beacon_data, (BROADCAST_ADDR, self.port))
            except:
                pass
            
            self.msleep(DISCOVERY_INTERVAL * 1000)
        
        sock.close()
    
    def stop(self):
        self.running = False
        self.wait(1000)


class FileTransferThread(QThread):
    """Background thread for file transfers"""
    progress = pyqtSignal(int, int, str)  # current, total, speed
    completed = pyqtSignal(bool, str)  # success, message
    log = pyqtSignal(str)
    
    def __init__(self, mode, **kwargs):
        super().__init__()
        self.mode = mode  # 'send' or 'receive'
        self.kwargs = kwargs
        self.running = True
        
    def run(self):
        try:
            if self.mode == 'send':
                self._send_file()
            else:
                self._receive_file()
        except Exception as e:
            self.completed.emit(False, str(e))
    
    def stop(self):
        self.running = False
    
    def _calculate_hash(self, filepath):
        """Calculate MD5 hash for file integrity"""
        hash_md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _send_file(self):
        filepath = self.kwargs['filepath']
        host = self.kwargs['host']
        port = self.kwargs['port']
        
        if not os.path.exists(filepath):
            self.completed.emit(False, f"File not found: {filepath}")
            return
        
        filesize = os.path.getsize(filepath)
        filename = os.path.basename(filepath)
        
        self.log.emit(f"Connecting to {host}:{port}...")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        
        try:
            sock.connect((host, port))
            
            # Send file metadata
            metadata = {
                'filename': filename,
                'size': filesize,
                'hash': self._calculate_hash(filepath)
            }
            meta_json = json.dumps(metadata).encode()
            sock.sendall(len(meta_json).to_bytes(4, 'big'))
            sock.sendall(meta_json)
            
            self.log.emit(f"Sending {filename} ({self._format_size(filesize)})...")
            
            # Send file data with progress
            sent = 0
            start_time = datetime.now()
            
            with open(filepath, 'rb') as f:
                while sent < filesize and self.running:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    sock.sendall(chunk)
                    sent += len(chunk)
                    
                    # Calculate speed
                    elapsed = (datetime.now() - start_time).total_seconds()
                    speed = sent / elapsed if elapsed > 0 else 0
                    
                    self.progress.emit(sent, filesize, self._format_speed(speed))
            
            if self.running:
                # Wait for acknowledgment
                response = sock.recv(1024).decode()
                if response == "OK":
                    self.completed.emit(True, f"Sent {filename} successfully!")
                else:
                    self.completed.emit(False, f"Transfer failed: {response}")
            else:
                self.completed.emit(False, "Transfer cancelled")
                
        except Exception as e:
            self.completed.emit(False, f"Transfer error: {str(e)}")
        finally:
            sock.close()
    
    def _receive_file(self):
        save_dir = self.kwargs['save_dir']
        port = self.kwargs['port']
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            sock.bind(('0.0.0.0', port))
            sock.listen(1)
            
            self.log.emit(f"Waiting for connection on port {port}...")
            
            conn, addr = sock.accept()
            self.log.emit(f"Connected from {addr[0]}")
            
            # Receive metadata length
            meta_len = int.from_bytes(conn.recv(4), 'big')
            metadata = json.loads(conn.recv(meta_len).decode())
            
            filename = metadata['filename']
            filesize = metadata['size']
            file_hash = metadata['hash']
            
            save_path = os.path.join(save_dir, filename)
            
            # Handle duplicate filenames
            counter = 1
            base, ext = os.path.splitext(save_path)
            while os.path.exists(save_path):
                save_path = f"{base}_{counter}{ext}"
                counter += 1
            
            self.log.emit(f"Receiving {filename} ({self._format_size(filesize)})...")
            
            # Receive file data
            received = 0
            start_time = datetime.now()
            
            with open(save_path, 'wb') as f:
                while received < filesize and self.running:
                    chunk = conn.recv(min(CHUNK_SIZE, filesize - received))
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
                    
                    elapsed = (datetime.now() - start_time).total_seconds()
                    speed = received / elapsed if elapsed > 0 else 0
                    
                    self.progress.emit(received, filesize, self._format_speed(speed))
            
            if self.running:
                # Verify hash
                self.log.emit("Verifying file integrity...")
                received_hash = self._calculate_hash(save_path)
                
                if received_hash == file_hash:
                    conn.sendall(b"OK")
                    self.completed.emit(True, f"Received {filename} to {save_path}")
                else:
                    conn.sendall(b"HASH_MISMATCH")
                    os.remove(save_path)
                    self.completed.emit(False, "File integrity check failed!")
            else:
                conn.sendall(b"CANCELLED")
                if os.path.exists(save_path):
                    os.remove(save_path)
                self.completed.emit(False, "Transfer cancelled")
                
        except Exception as e:
            self.completed.emit(False, f"Receive error: {str(e)}")
        finally:
            sock.close()
    
    def _format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"
    
    def _format_speed(self, speed):
        return f"{self._format_size(speed)}/s"


class ModernStyle:
    """Modern dark theme styling"""
    
    @staticmethod
    def apply(app):
        app.setStyle('Fusion')
        palette = QPalette()
        
        # Dark theme colors
        palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Base, QColor(45, 45, 45))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 212))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
        
        app.setPalette(palette)
        
        # Stylesheet for additional customization
        app.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QGroupBox {
                border: 2px solid #3d3d3d;
                border-radius: 8px;
                margin-top: 10px;
                font-weight: bold;
                color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #888888;
            }
            QLineEdit {
                background-color: #2d2d2d;
                color: white;
                border: 2px solid #3d3d3d;
                border-radius: 5px;
                padding: 8px;
            }
            QLineEdit:focus {
                border: 2px solid #0078d4;
            }
            QTextEdit {
                background-color: #2d2d2d;
                color: #00ff00;
                border: 2px solid #3d3d3d;
                border-radius: 5px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
            QProgressBar {
                border: 2px solid #3d3d3d;
                border-radius: 5px;
                text-align: center;
                color: white;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
            QTableWidget {
                background-color: #2d2d2d;
                color: white;
                border: 2px solid #3d3d3d;
                gridline-color: #3d3d3d;
            }
            QTableWidget::item:selected {
                background-color: #0078d4;
            }
            QHeaderView::section {
                background-color: #3d3d3d;
                color: white;
                padding: 5px;
                border: 1px solid #555555;
            }
            QTabWidget::pane {
                border: 2px solid #3d3d3d;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #3d3d3d;
                color: white;
                padding: 10px 20px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #0078d4;
            }
            QTabBar::tab:hover:!selected {
                background-color: #505050;
            }
            QListWidget {
                background-color: #2d2d2d;
                color: white;
                border: 2px solid #3d3d3d;
                border-radius: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #3d3d3d;
            }
            QListWidget::item:selected {
                background-color: #0078d4;
            }
            QListWidget::item:hover {
                background-color: #3d3d3d;
            }
        """)


class FlashTransferApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("⚡ FlashTransfer - Fast File Transfer")
        self.setMinimumSize(1000, 800)
        
        self.transfer_thread = None
        self.discovery_thread = None
        self.history = []
        self.discovered_devices = {}  # ip -> {hostname, platform}
        
        self.init_ui()
        self.setup_discovery()
        self.setup_auto_refresh()
    
    def init_ui(self):
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel("⚡ FlashTransfer")
        header.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("color: #0078d4; margin-bottom: 5px;")
        layout.addWidget(header)
        
        subtitle = QLabel("Auto-Discovering File Transfer (Linux ↔ Windows)")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #888888; margin-bottom: 10px;")
        layout.addWidget(subtitle)
        
        # Discovered Devices Banner
        devices_banner = QLabel("🔍 Auto-Discovery Active - Looking for devices on network...")
        devices_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        devices_banner.setStyleSheet("background-color: #0078d4; color: white; padding: 8px; border-radius: 5px;")
        layout.addWidget(devices_banner)
        self.devices_banner = devices_banner
        
        # Tabs
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Send Tab
        send_tab = self.create_send_tab()
        tabs.addTab(send_tab, "📤 Send File")
        
        # Receive Tab
        receive_tab = self.create_receive_tab()
        tabs.addTab(receive_tab, "📥 Receive File")
        
        # Devices Tab
        devices_tab = self.create_devices_tab()
        tabs.addTab(devices_tab, "📱 Devices")
        
        # History Tab
        history_tab = self.create_history_tab()
        tabs.addTab(history_tab, "📋 History")
        
        # Status bar
        self.status = QLabel("Ready - Auto-discovery running")
        self.status.setStyleSheet("color: #888888; padding: 5px;")
        layout.addWidget(self.status)
    
    def create_send_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        # Discovered Devices Section
        devices_group = QGroupBox("📱 Discovered Devices (Click to Connect)")
        devices_layout = QVBoxLayout(devices_group)
        
        self.devices_list = QListWidget()
        self.devices_list.itemClicked.connect(self.on_device_selected)
        self.devices_list.setMaximumHeight(120)
        devices_layout.addWidget(self.devices_list)
        
        self.refresh_devices_btn = QPushButton("🔄 Refresh Devices")
        self.refresh_devices_btn.clicked.connect(self.refresh_devices)
        devices_layout.addWidget(self.refresh_devices_btn)
        
        layout.addWidget(devices_group)
        
        # File Selection
        file_group = QGroupBox("File Selection")
        file_layout = QVBoxLayout(file_group)
        
        file_hlayout = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Select a file to send...")
        file_hlayout.addWidget(self.file_path)
        
        browse_btn = QPushButton("📁 Browse")
        browse_btn.clicked.connect(self.browse_file)
        file_hlayout.addWidget(browse_btn)
        
        file_layout.addLayout(file_hlayout)
        
        self.file_info = QLabel("No file selected")
        self.file_info.setStyleSheet("color: #888888;")
        file_layout.addWidget(self.file_info)
        
        layout.addWidget(file_group)
        
        # Connection Settings
        conn_group = QGroupBox("Connection Settings")
        conn_layout = QVBoxLayout(conn_group)
        
        # Host
        host_layout = QHBoxLayout()
        host_layout.addWidget(QLabel("Target IP Address:"))
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("Select from discovered devices or type manually...")
        host_layout.addWidget(self.host_input)
        conn_layout.addLayout(host_layout)
        
        # Port
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(DEFAULT_PORT)
        port_layout.addWidget(self.port_input)
        port_layout.addStretch()
        conn_layout.addLayout(port_layout)
        
        # My IP info
        my_ip = self.get_local_ip()
        ip_label = QLabel(f"💡 Your IP: {my_ip} (Share this with sender)")
        ip_label.setStyleSheet("color: #00ff00;")
        conn_layout.addWidget(ip_label)
        
        layout.addWidget(conn_group)
        
        # Progress
        progress_group = QGroupBox("Transfer Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.send_progress = QProgressBar()
        self.send_progress.setMaximum(100)
        self.send_progress.setTextVisible(True)
        progress_layout.addWidget(self.send_progress)
        
        self.speed_label = QLabel("Speed: -")
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.speed_label)
        
        layout.addWidget(progress_group)
        
        # Log
        log_group = QGroupBox("Transfer Log")
        log_layout = QVBoxLayout(log_group)
        
        self.send_log = QTextEdit()
        self.send_log.setReadOnly(True)
        log_layout.addWidget(self.send_log)
        
        layout.addWidget(log_group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.send_btn = QPushButton("🚀 Start Transfer")
        self.send_btn.clicked.connect(self.start_send)
        btn_layout.addWidget(self.send_btn)
        
        self.cancel_send_btn = QPushButton("❌ Cancel")
        self.cancel_send_btn.clicked.connect(self.cancel_transfer)
        self.cancel_send_btn.setEnabled(False)
        btn_layout.addWidget(self.cancel_send_btn)
        
        layout.addLayout(btn_layout)
        layout.addStretch()
        
        return widget
    
    def create_receive_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        # Settings
        settings_group = QGroupBox("Receive Settings")
        settings_layout = QVBoxLayout(settings_group)
        
        # Save directory
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("Save to:"))
        self.save_dir = QLineEdit()
        self.save_dir.setText(str(Path.home() / "Downloads"))
        dir_layout.addWidget(self.save_dir)
        
        dir_btn = QPushButton("📁 Browse")
        dir_btn.clicked.connect(self.browse_save_dir)
        dir_layout.addWidget(dir_btn)
        settings_layout.addLayout(dir_layout)
        
        # Port
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Listen Port:"))
        self.recv_port = QSpinBox()
        self.recv_port.setRange(1024, 65535)
        self.recv_port.setValue(DEFAULT_PORT)
        port_layout.addWidget(self.recv_port)
        port_layout.addStretch()
        settings_layout.addLayout(port_layout)
        
        # My IP
        my_ip = self.get_local_ip()
        recv_ip_label = QLabel(f"💡 Your IP: {my_ip}\nShare this IP with the sender")
        recv_ip_label.setStyleSheet("color: #00ff00; font-size: 14px;")
        recv_ip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        settings_layout.addWidget(recv_ip_label)
        
        layout.addWidget(settings_group)
        
        # Progress
        recv_progress_group = QGroupBox("Receive Progress")
        recv_progress_layout = QVBoxLayout(recv_progress_group)
        
        self.recv_progress = QProgressBar()
        self.recv_progress.setMaximum(100)
        recv_progress_layout.addWidget(self.recv_progress)
        
        self.recv_speed_label = QLabel("Waiting...")
        self.recv_speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recv_progress_layout.addWidget(self.recv_speed_label)
        
        layout.addWidget(recv_progress_group)
        
        # Log
        recv_log_group = QGroupBox("Receive Log")
        recv_log_layout = QVBoxLayout(recv_log_group)
        
        self.recv_log = QTextEdit()
        self.recv_log.setReadOnly(True)
        recv_log_layout.addWidget(self.recv_log)
        
        layout.addWidget(recv_log_group)
        
        # Buttons
        recv_btn_layout = QHBoxLayout()
        
        self.listen_btn = QPushButton("👂 Start Listening")
        self.listen_btn.clicked.connect(self.start_receive)
        recv_btn_layout.addWidget(self.listen_btn)
        
        self.stop_listen_btn = QPushButton("🛑 Stop")
        self.stop_listen_btn.clicked.connect(self.cancel_transfer)
        self.stop_listen_btn.setEnabled(False)
        recv_btn_layout.addWidget(self.stop_listen_btn)
        
        layout.addLayout(recv_btn_layout)
        layout.addStretch()
        
        return widget
    
    def create_devices_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Header
        header = QLabel("📱 Discovered FlashTransfer Devices")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Description
        desc = QLabel("These devices are running FlashTransfer on your network. Click to auto-fill IP.")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #888888;")
        layout.addWidget(desc)
        
        # Devices table
        self.devices_table = QTableWidget()
        self.devices_table.setColumnCount(4)
        self.devices_table.setHorizontalHeaderLabels(["IP Address", "Hostname", "Platform", "Status"])
        self.devices_table.horizontalHeader().setStretchLastSection(True)
        self.devices_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.devices_table.itemClicked.connect(self.on_table_device_selected)
        layout.addWidget(self.devices_table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 Scan Network")
        refresh_btn.clicked.connect(self.refresh_devices)
        btn_layout.addWidget(refresh_btn)
        
        clear_btn = QPushButton("🗑️ Clear List")
        clear_btn.clicked.connect(self.clear_devices)
        btn_layout.addWidget(clear_btn)
        
        layout.addLayout(btn_layout)
        
        return widget
    
    def create_history_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels([
            "Time", "Type", "File", "Size", "Status"
        ])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        layout.addWidget(self.history_table)
        
        # Clear button
        clear_btn = QPushButton("🗑️ Clear History")
        clear_btn.clicked.connect(self.clear_history)
        layout.addWidget(clear_btn)
        
        return widget
    
    def setup_discovery(self):
        """Start device discovery thread"""
        self.discovery_thread = DiscoveryThread()
        self.discovery_thread.device_found.connect(self.on_device_found)
        self.discovery_thread.device_lost.connect(self.on_device_lost)
        self.discovery_thread.log.connect(self.log_discovery)
        self.discovery_thread.start()
    
    def on_device_found(self, ip, hostname, platform):
        """Handle newly discovered device"""
        if ip not in self.discovered_devices:
            self.discovered_devices[ip] = {
                'hostname': hostname,
                'platform': platform,
                'last_seen': datetime.now()
            }
            
            # Update list widget
            self.update_devices_list()
            
            # Update table
            self.update_devices_table()
            
            # Update banner
            self.devices_banner.setText(f"🔍 Found {len(self.discovered_devices)} device(s) on network")
            self.devices_banner.setStyleSheet("background-color: #00aa00; color: white; padding: 8px; border-radius: 5px;")
            
            self.status.setText(f"Discovered: {hostname} ({ip})")
    
    def on_device_lost(self, ip):
        """Handle device timeout"""
        if ip in self.discovered_devices:
            del self.discovered_devices[ip]
            self.update_devices_list()
            self.update_devices_table()
            
            if len(self.discovered_devices) == 0:
                self.devices_banner.setText("🔍 Auto-Discovery Active - Looking for devices...")
                self.devices_banner.setStyleSheet("background-color: #0078d4; color: white; padding: 8px; border-radius: 5px;")
    
    def update_devices_list(self):
        """Update the devices list widget"""
        self.devices_list.clear()
        
        for ip, info in self.discovered_devices.items():
            platform_icon = "🐧" if "linux" in info['platform'].lower() else "🪟" if "win" in info['platform'].lower() else "💻"
            item_text = f"{platform_icon} {info['hostname']} ({ip})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, ip)
            self.devices_list.addItem(item)
        
        if self.devices_list.count() == 0:
            self.devices_list.addItem("No devices found yet... Make sure other devices are running FlashTransfer")
    
    def update_devices_table(self):
        """Update the devices table"""
        self.devices_table.setRowCount(len(self.discovered_devices))
        
        for row, (ip, info) in enumerate(self.discovered_devices.items()):
            self.devices_table.setItem(row, 0, QTableWidgetItem(ip))
            self.devices_table.setItem(row, 1, QTableWidgetItem(info['hostname']))
            self.devices_table.setItem(row, 2, QTableWidgetItem(info['platform']))
            
            last_seen = (datetime.now() - info['last_seen']).seconds
            status = "🟢 Online" if last_seen < 5 else "🟡 Away" if last_seen < 15 else "🔴 Offline"
            self.devices_table.setItem(row, 3, QTableWidgetItem(status))
    
    def on_device_selected(self, item):
        """Handle device selection from list"""
        ip = item.data(Qt.ItemDataRole.UserRole)
        if ip:
            self.host_input.setText(ip)
            self.status.setText(f"Selected device: {ip}")
    
    def on_table_device_selected(self, item):
        """Handle device selection from table"""
        row = item.row()
        ip = self.devices_table.item(row, 0).text()
        self.host_input.setText(ip)
        self.status.setText(f"Selected device: {ip}")
    
    def refresh_devices(self):
        """Manually refresh device list"""
        self.status.setText("Scanning network...")
        # Force a discovery broadcast by briefly restarting discovery
        if self.discovery_thread:
            self.discovery_thread.stop()
            self.discovery_thread.wait()
        
        self.discovery_thread = DiscoveryThread()
        self.discovery_thread.device_found.connect(self.on_device_found)
        self.discovery_thread.device_lost.connect(self.on_device_lost)
        self.discovery_thread.log.connect(self.log_discovery)
        self.discovery_thread.start()
        
        self.status.setText("Network scan started")
    
    def clear_devices(self):
        """Clear discovered devices"""
        self.discovered_devices.clear()
        self.update_devices_list()
        self.update_devices_table()
    
    def log_discovery(self, msg):
        """Log discovery messages"""
        pass  # Silent discovery
    
    def get_local_ip(self):
        """Get local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select File to Send")
        if path:
            self.file_path.setText(path)
            size = os.path.getsize(path)
            self.file_info.setText(f"📄 {os.path.basename(path)} ({self.format_size(size)})")
    
    def browse_save_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if path:
            self.save_dir.setText(path)
    
    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"
    
    def start_send(self):
        filepath = self.file_path.text()
        host = self.host_input.text()
        port = self.port_input.value()
        
        if not filepath or not os.path.exists(filepath):
            QMessageBox.warning(self, "Error", "Please select a valid file!")
            return
        
        if not host:
            QMessageBox.warning(self, "Error", "Please enter target IP address or select a discovered device!")
            return
        
        self.send_btn.setEnabled(False)
        self.cancel_send_btn.setEnabled(True)
        self.send_progress.setValue(0)
        self.send_log.clear()
        
        self.transfer_thread = FileTransferThread(
            'send', filepath=filepath, host=host, port=port
        )
        self.transfer_thread.progress.connect(self.update_send_progress)
        self.transfer_thread.completed.connect(self.transfer_completed)
        self.transfer_thread.log.connect(self.log_send)
        self.transfer_thread.start()
    
    def start_receive(self):
        save_dir = self.save_dir.text()
        port = self.recv_port.value()
        
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        
        self.listen_btn.setEnabled(False)
        self.stop_listen_btn.setEnabled(True)
        self.recv_progress.setValue(0)
        self.recv_log.clear()
        
        self.transfer_thread = FileTransferThread(
            'receive', save_dir=save_dir, port=port
        )
        self.transfer_thread.progress.connect(self.update_recv_progress)
        self.transfer_thread.completed.connect(self.transfer_completed)
        self.transfer_thread.log.connect(self.log_recv)
        self.transfer_thread.start()
        
        self.status.setText(f"Listening on port {port}...")
    
    def cancel_transfer(self):
        if self.transfer_thread:
            self.transfer_thread.stop()
            self.transfer_thread.wait(1000)
        
        self.send_btn.setEnabled(True)
        self.cancel_send_btn.setEnabled(False)
        self.listen_btn.setEnabled(True)
        self.stop_listen_btn.setEnabled(False)
        self.status.setText("Cancelled")
    
    def update_send_progress(self, current, total, speed):
        percent = int((current / total) * 100)
        self.send_progress.setValue(percent)
        self.speed_label.setText(f"Speed: {speed}")
    
    def update_recv_progress(self, current, total, speed):
        percent = int((current / total) * 100)
        self.recv_progress.setValue(percent)
        self.recv_speed_label.setText(f"Receiving... {speed}")
    
    def transfer_completed(self, success, message):
        self.send_btn.setEnabled(True)
        self.cancel_send_btn.setEnabled(False)
        self.listen_btn.setEnabled(True)
        self.stop_listen_btn.setEnabled(False)
        
        if success:
            self.status.setText(f"✅ {message}")
            QMessageBox.information(self, "Success", message)
        else:
            self.status.setText(f"❌ {message}")
            QMessageBox.critical(self, "Error", message)
        
        # Add to history
        self.add_to_history(
            "Send" if self.sender() else "Receive",
            self.file_path.text() if hasattr(self, 'file_path') else "Received file",
            "Success" if success else "Failed"
        )
    
    def log_send(self, msg):
        self.send_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    
    def log_recv(self, msg):
        self.recv_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    
    def add_to_history(self, type_, file_, status):
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        self.history_table.setItem(row, 0, QTableWidgetItem(datetime.now().strftime("%Y-%m-%d %H:%M")))
        self.history_table.setItem(row, 1, QTableWidgetItem(type_))
        self.history_table.setItem(row, 2, QTableWidgetItem(os.path.basename(file_)))
        size = os.path.getsize(file_) if os.path.exists(file_) else 0
        self.history_table.setItem(row, 3, QTableWidgetItem(self.format_size(size)))
        self.history_table.setItem(row, 4, QTableWidgetItem(status))
    
    def clear_history(self):
        self.history_table.setRowCount(0)
    
    def setup_auto_refresh(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_ui)
        self.timer.start(1000)
    
    def refresh_ui(self):
        # Update device status in table
        self.update_devices_table()
    
    def closeEvent(self, event):
        """Clean up threads on close"""
        if self.discovery_thread:
            self.discovery_thread.stop()
        if self.transfer_thread:
            self.transfer_thread.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    
    # Apply modern dark theme
    ModernStyle.apply(app)
    
    window = FlashTransferApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
