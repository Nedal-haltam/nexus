import sys
import socket
import json
import struct
import threading
import os
import base64
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QListWidget, QTextEdit, QSplitter, QGroupBox, QMessageBox, QListWidgetItem)
from PySide6.QtCore import Qt, Signal, QObject, Slot
from PySide6.QtGui import QImage, QPixmap, QTextCursor

MAX_LOG_SIZE = 1024
DELETE_LOG_SIZE = 512

def send_json(sock, data_dict):
    try:
        json_bytes = json.dumps(data_dict).encode('utf-8')
        message = struct.pack('>I', len(json_bytes)) + json_bytes
        sock.sendall(message)
    except Exception as e:
        print(f"Send Error: {e}")

def recv_json(sock):
    try:
        raw_len = recv_all(sock, 4)
        if not raw_len: return None
        msg_len = struct.unpack('>I', raw_len)[0]
        
        payload = recv_all(sock, msg_len)
        if not payload: return None
        return json.loads(payload.decode('utf-8'))
    except Exception:
        return None

def recv_all(sock, n):
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet: return None
        data += packet
    return data

class ServerSignals(QObject):
    log = Signal(str)
    client_connected = Signal(str, object)
    client_disconnected = Signal(str)
    image_received = Signal(str, str, str, str)

class NetworkServer(QObject):
    def __init__(self, port=5000):
        super().__init__()
        self.port = port
        self.running = False
        self.server_socket = None
        self.signals = ServerSignals()
        self.clients = {}
        self.client_history = {}

    def start_server(self):
        self.running = True
        threading.Thread(target=self._listen_loop, daemon=True).start()

    def _listen_loop(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(10)
            self.signals.log.emit(f"Server listening on port {self.port}")

            while self.running:
                client_sock, addr = self.server_socket.accept()
                ip_id = f"{addr[0]}:{addr[1]}"
                
                self.clients[ip_id] = client_sock
                self.client_history[ip_id] = []
                self.signals.client_connected.emit(ip_id, client_sock)
                self.signals.log.emit(f"New connection: {ip_id}")
                
                threading.Thread(target=self._handle_client, args=(client_sock, ip_id), daemon=True).start()
        except Exception as e:
            self.signals.log.emit(f"Server Error: {e}")

    def _handle_client(self, conn, ip_id):
        try:
            while self.running:
                data = recv_json(conn)
                if not data:
                    break
                
                if data.get('type') == 'response':
                    img_b64 = data.get('image', '')
                    ts = data.get('timestamp', '')
                    client_ip = data.get('client_ip', '')
                    
                    # self._save_data(client_ip, ts, img_b64)
                    self.signals.image_received.emit(client_ip, ts, img_b64, json.dumps(data, indent=2))
        except Exception as e:
            self.signals.log.emit(f"Client {ip_id} error: {e}")
        finally:
            conn.close()
            if ip_id in self.clients: del self.clients[ip_id]
            if ip_id in self.client_history: del self.client_history[ip_id]
            self.signals.client_disconnected.emit(ip_id)
            self.signals.log.emit(f"Client disconnected: {ip_id}")

    def _save_data(self, client_ip, timestamp, img_b64):
        try:
            clean_ip = client_ip.replace(':', '_')
            folder = os.path.join("received_data", clean_ip)
            os.makedirs(folder, exist_ok=True)
            
            filename = f"{timestamp.replace(':','-')}.png"
            path = os.path.join(folder, filename)
            
            img_data = base64.b64decode(img_b64)
            with open(path, "wb") as f:
                f.write(img_data)
        except Exception as e:
            print(f"Failed to save data: {e}")

    def _add_to_history(self, client_id, command):
        if client_id not in self.client_history:
            self.client_history[client_id] = []
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {command}"

        self.client_history[client_id].append(entry)

        if len(self.client_history[client_id]) > 10:
            self.client_history[client_id].pop(0)

    def send_command(self, target_ip, command):
        payload = {"type": "query", "command": command}
        
        if target_ip == "BROADCAST":
            for ip, sock in list(self.clients.items()):
                try:
                    send_json(sock, payload)
                    self._add_to_history(ip, command)
                except:
                    pass
            self.signals.log.emit(f"Broadcast sent: {command}")
        elif target_ip in self.clients:
            try:
                send_json(self.clients[target_ip], payload)
                self._add_to_history(target_ip, command)
                self.signals.log.emit(f"Sent to {target_ip}: {command}")
            except Exception as e:
                self.signals.log.emit(f"Send failed: {e}")
        else:
            self.signals.log.emit(f"Target {target_ip} not found.")

class ServerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Distributed Control Server")
        self.resize(1000, 750)
        
        self.server = NetworkServer()
        self.setup_ui()
        self.connect_signals()
        self.server.start_server()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        left_layout = QVBoxLayout()
        
        grp_clients = QGroupBox("Client Management")
        client_layout = QVBoxLayout()
        self.list_clients = QListWidget()

        self.list_clients.setToolTip("Double-click a client to see sent query history")

        remove_selected_btn = QPushButton("Remove Selected")
        remove_selected_btn.setStyleSheet("background-color: #ffcccc; color: darkred;")
        client_layout.addWidget(QLabel("Connected Clients:"))
        client_layout.addWidget(self.list_clients)
        client_layout.addWidget(remove_selected_btn)
        grp_clients.setLayout(client_layout)
                
        grp_query = QGroupBox("Query Panel")
        query_layout = QVBoxLayout()
        self.txt_query = QLineEdit()
        self.txt_query.setPlaceholderText("Enter Command Here...")
        btn_send = QPushButton("Send to Selected")
        btn_broadcast = QPushButton("Broadcast All")
        query_layout.addWidget(self.txt_query)
        query_layout.addWidget(btn_send)
        query_layout.addWidget(btn_broadcast)
        grp_query.setLayout(query_layout)
        
        grp_log = QGroupBox("System Logs")
        log_layout = QVBoxLayout()
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        log_layout.addWidget(self.txt_log)
        grp_log.setLayout(log_layout)

        left_layout.addWidget(grp_clients)
        left_layout.addWidget(grp_query)
        left_layout.addWidget(grp_log)
        
        right_layout = QVBoxLayout()
        grp_display = QGroupBox("Live Monitor")
        disp_layout = QVBoxLayout()
        
        self.lbl_image = QLabel("No Image")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setStyleSheet("border: 1px dashed gray; background: #eee;")
        self.lbl_image.setMinimumSize(400, 300)
        
        self.lbl_meta = QLabel("Metadata: Waiting...")
        self.lbl_meta.setWordWrap(True)
        
        disp_layout.addWidget(self.lbl_image, 1)
        disp_layout.addWidget(self.lbl_meta)
        grp_display.setLayout(disp_layout)
        
        right_layout.addWidget(grp_display)

        splitter = QSplitter(Qt.Horizontal)
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([350, 650])
        
        main_layout.addWidget(splitter)
        
        btn_send.clicked.connect(self.on_send_clicked)
        btn_broadcast.clicked.connect(self.on_broadcast_clicked)
        remove_selected_btn.clicked.connect(self.remove_client)

        self.list_clients.itemDoubleClicked.connect(self.show_client_history)

    def connect_signals(self):
        self.server.signals.log.connect(self.log)
        self.server.signals.client_connected.connect(self.add_client_to_list)
        self.server.signals.client_disconnected.connect(self.remove_client_from_list)
        self.server.signals.image_received.connect(self.update_display)

    def show_client_history(self, item):
        client_id = item.text()
        history = self.server.client_history.get(client_id, [])
        if not history:
            info_text = "No queries have been sent to this client yet."
        else:
            info_text = "\n".join(history)
        QMessageBox.information(self, f"History: {client_id}", info_text)

    @Slot(str)
    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        if self.txt_log.document().blockCount() >= MAX_LOG_SIZE:
            cursor = self.txt_log.textCursor()
            cursor.movePosition(QTextCursor.Start)
            for _ in range(DELETE_LOG_SIZE):
                cursor.movePosition(QTextCursor.NextBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        self.txt_log.append(f"[{ts}] {msg}")    

    @Slot(str, object)
    def add_client_to_list(self, ip_id, sock):
        item = QListWidgetItem(ip_id)
        item.setCheckState(Qt.Unchecked) 
        self.list_clients.addItem(item)

    @Slot(str)
    def remove_client_from_list(self, ip_id):
        items = self.list_clients.findItems(ip_id, Qt.MatchExactly)
        for item in items:
            self.list_clients.takeItem(self.list_clients.row(item))

    def remove_client(self):
        checked_clients = []
        for index in range(self.list_clients.count()):
            item = self.list_clients.item(index)
            if item.checkState() == Qt.Checked:
                checked_clients.append(item.text())

        if not checked_clients:
             QMessageBox.warning(self, "Warning", "Check clients to remove.")
             return

        for ip_id in checked_clients:
            if ip_id in self.server.clients:
                try: self.server.clients[ip_id].close()
                except: pass

    def on_send_clicked(self):
        checked_clients = []
        for index in range(self.list_clients.count()):
            item = self.list_clients.item(index)
            if item.checkState() == Qt.Checked:
                checked_clients.append(item.text())

        if not checked_clients:
            QMessageBox.warning(self, "Warning", "Check at least one client to send to.")
            return

        cmd = self.txt_query.text()
        if cmd:
            for ip in checked_clients:
                self.server.send_command(ip, cmd)
        self.txt_query.clear()

    def on_broadcast_clicked(self):
        cmd = self.txt_query.text()
        if cmd:
            self.server.send_command("BROADCAST", cmd)

    @Slot(str, str, str, str)
    def update_display(self, ip, ts, b64_img, meta):
        self.log(f"ALERT: Response received from {ip}")
        self.lbl_meta.setText(f"<b>Source:</b> {ip}<br><b>Time:</b> {ts}")
        
        try:
            img_data = base64.b64decode(b64_img)
            qimg = QImage.fromData(img_data)
            pixmap = QPixmap.fromImage(qimg)
            self.lbl_image.setPixmap(pixmap.scaled(self.lbl_image.size(), Qt.KeepAspectRatio))
        except Exception as e:
            self.log(f"Error decoding image: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ServerGUI()
    window.show()
    sys.exit(app.exec())