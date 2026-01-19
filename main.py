from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QGroupBox, QFormLayout)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap, QIntValidator

import sys
import cv2
import time
import os
from ultralytics import YOLO
import threading
import torch
import queue

WIDTH = 640
HEIGHT = 480
DEFAULT_FPS = 30
# DETECTION_SKIP_FRAMES = 30
STATUS_CONNECTING_COLOR = "blue"
STATUS_CONNECTED_COLOR = "green"
STATUS_DISCONNECTED_COLOR = "orange"
STATUS_ERROR_COLOR = "red"
AUTO_RECONNECT = True

MODEL_PATH = "./models/yolov8s-world.pt"
# MODEL_PATH = "./models/yolov8s-worldv2.pt"
# MODEL_PATH = "./models/yolov8m-worldv2.pt"

model : YOLO = None
classes : list[str] = []
command_queue : queue.Queue = queue.Queue()

def load_model(model_path):
    print("Loading model...")
    # device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
    device = 'cpu'
    print(f"Using device: {device}")
    
    model = YOLO(model_path)
    model.to(device)
    return model

def detect_objects(frame, model : YOLO, classes : list[str]):
    results = model.predict(frame, verbose=False)    
    return results[0].plot()

def input_thread(command_queue):
    print("Input thread started. Enter +class to add or -class to remove (e.g., +cat, -dog).")
    while True:
        try:
            user_input = input().strip()
            command_queue.put(user_input)
        except EOFError:
            break
        except Exception as e:
            pass

def update_model_classes():
    global command_queue, classes, model
    updated_classes = False
    while not command_queue.empty():
        updated_classes = True
        command = command_queue.get()
        try:
            action = command[0]
            class_name = command[1:].strip()
            if action == '+' and class_name and class_name not in classes:
                classes.append(class_name)
            elif action == '-' and class_name in classes:
                classes.remove(class_name)
            print(f"Updated classes: {classes}")
        except Exception as e:
            print(f"Command Error: {e}")
    if updated_classes:
        target_classes = classes if classes else ['']
        model.set_classes(target_classes)

class VideoThread(QThread):
    vt_signal_update_image = Signal(QImage)
    vt_signal_update_fps_label = Signal(str)
    vt_signal_update_resolution_label = Signal(str, str)
    vt_signal_update_status_label = Signal(str, str)
    vt_signal_update_error_label = Signal(str)
    vt_signal_reset_ui_state = Signal()
    vt_signal_disable_connect_button = Signal()
    vt_signal_enable_connect_button = Signal()

    vt_signal_connection_failed = Signal(str)
    vt_signal_connection_retain = Signal()
    
    def __init__(self):
        super().__init__()
        self._run_flag = True
        self.rtsp_url = ""
        self.target_fps = DEFAULT_FPS
        self.last_frame_time = 0
        self.incoming_width = 0
        self.incoming_height = 0
        self.last_results = None
        # self.frame_counter = 0
        
        self.cap : cv2.VideoCapture = None
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.capture_thread = None

    def init_video_capture(self) -> bool:
        self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000
        ])
        if not self.cap.isOpened():
            return False

        # self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.incoming_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.incoming_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return True

    def reconnect_to_camera(self) -> bool:
        while self._run_flag:
            self.vt_signal_disable_connect_button.emit()
            ret = self.init_video_capture()
            self.vt_signal_enable_connect_button.emit()
            if ret:
                return True
            for _ in range(20):
                if not self._run_flag: return False
                time.sleep(0.1)
        return False
    
    def connect_to_camera(self) -> bool:
        self.vt_signal_disable_connect_button.emit()
        ret = self.init_video_capture()
        self.vt_signal_enable_connect_button.emit()
        return ret

    def cvimage_to_qimage(self, cv_img : cv2.typing.MatLike) -> QImage:
        rgb_image : cv2.typing.MatLike = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        return convert_to_qt_format.scaled(WIDTH, HEIGHT, Qt.AspectRatioMode.KeepAspectRatio)

    def incoming_res(self) -> str: return f"{self.incoming_width}x{self.incoming_height}"

    def draw_detections(self, frame, results):
        if results is None: return frame
        
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])

            try:
                label_name = results.names[cls_id]
            except:
                label_name = ''
            label_text = f"{label_name} {conf:.2f}"

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            # detected_image = frame[y1:y2, x1:x2]
            (w, h), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - 20), (x1 + w, y1), (0, 255, 0), -1)
            cv2.putText(frame, label_text, (x1, y1 - 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
        return frame

    def capture_worker(self):
        self.vt_signal_update_status_label.emit("Connecting...", STATUS_CONNECTING_COLOR)
        if not self.connect_to_camera():
            self.vt_signal_update_status_label.emit("Disconnected", STATUS_DISCONNECTED_COLOR)
            self.vt_signal_connection_failed.emit(f"Failed to open {self.rtsp_url}")
            return
        self.vt_signal_update_status_label.emit("Connected", STATUS_CONNECTED_COLOR)

        while self._run_flag:
            if not self.cap.isOpened() or not self.cap.grab():
                self.vt_signal_update_status_label.emit("ReConnecting...", STATUS_CONNECTING_COLOR)
                self.vt_signal_update_error_label.emit("Stream lost")
                
                with self.frame_lock:
                    self.latest_frame = None

                if not AUTO_RECONNECT:
                    break
                else:
                    if not self.reconnect_to_camera():
                        break
                    self.vt_signal_update_status_label.emit("Connected", STATUS_CONNECTED_COLOR)
                    continue
            
            ret, frame = self.cap.retrieve()
            if ret:
                with self.frame_lock:
                    self.latest_frame = frame
            
            # time.sleep(0.005) 

        if self.cap:
            self.cap.release()


    def run(self):
        global command_queue, classes, model

        self.capture_thread = threading.Thread(target=self.capture_worker, daemon=True)
        self.capture_thread.start()

        while self._run_flag:
            
            update_model_classes()

            current_time = time.time()
            time_diff = current_time - self.last_frame_time
            if time_diff >= (1.0 / self.target_fps):
                working_frame = None
                with self.frame_lock:
                    if self.latest_frame is not None:
                        working_frame = self.latest_frame.copy()
                if working_frame is None:
                    time.sleep(0.01)
                    continue

                self.last_frame_time = current_time
                cv_img = cv2.resize(working_frame, (WIDTH, HEIGHT))

                # self.frame_counter += 1
                # if self.frame_counter % DETECTION_SKIP_FRAMES == 0:
                if True:
                    results = model.predict(cv_img, verbose=False, device=model.device)
                    self.last_results = results[0]
                
                final_img = self.draw_detections(cv_img, self.last_results)

                p = self.cvimage_to_qimage(final_img)
                self.vt_signal_update_resolution_label.emit(self.incoming_res(), f"{p.width()}x{p.height()}")
                actual_fps = 1.0 / time_diff
                self.vt_signal_update_fps_label.emit(f"{actual_fps:.1f}")
                self.vt_signal_update_image.emit(p)
                self.vt_signal_connection_retain.emit()
            
            if self.capture_thread and not self.capture_thread.is_alive():
                break

        if self.capture_thread.is_alive():
            self.capture_thread.join(timeout=1.0)
        
        self.vt_signal_reset_ui_state.emit()

    def stop(self):
        self._run_flag = False
        self.wait()

class CameraApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.fps = DEFAULT_FPS
        self.setWindowTitle("IP Camera Viewer - Nexus")
        self.setGeometry(100, 100, 950, 650)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout()
        self.central_widget.setLayout(self.main_layout)

        self._init_ui_components()
        self.current_vt = None

    def _init_ui_components(self):
        self._setup_video_panel()
        self._setup_controls_panel()

    def _setup_video_panel(self):
        self.video_label = QLabel("Video Stream Disconnected")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; color: white;")
        self.video_label.setMinimumSize(WIDTH, HEIGHT)
        self.main_layout.addWidget(self.video_label, stretch=2)

    def _setup_controls_panel(self):
        self.controls_panel = QWidget()
        self.controls_layout = QVBoxLayout()
        self.controls_panel.setLayout(self.controls_layout)
        
        self._create_camera_config_group()
        self._create_fps_control_group()
        self._create_control_unit_group()
        self._create_status_group()

        self.controls_layout.addStretch()
        self.main_layout.addWidget(self.controls_panel, stretch=1)

    def _create_camera_config_group(self):
        group = QGroupBox("Camera Configuration")
        layout = QFormLayout()
        
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("rtsp://username:passwd@IP:port")
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        
        layout.addRow("Camera IP/URL:", self.ip_input)
        layout.addRow(self.connect_btn)
        group.setLayout(layout)
        self.controls_layout.addWidget(group)

    def _create_fps_control_group(self):
        group = QGroupBox("FPS Control (Client-Side)")
        layout = QFormLayout()
        fps_container = QWidget()
        fps_layout = QHBoxLayout()
        fps_layout.setContentsMargins(0, 0, 0, 0)
        
        self.fps_input = QLineEdit()
        # self.fps_input.setValidator(QIntValidator(1, 60))
        self.fps_input.setText(f'{DEFAULT_FPS}')
        
        self.fps_btn = QPushButton("Update")
        self.fps_btn.clicked.connect(self.update_fps)

        fps_layout.addWidget(self.fps_input)
        fps_layout.addWidget(self.fps_btn)
        fps_container.setLayout(fps_layout)
        
        layout.addRow("Target FPS:", fps_container)
        group.setLayout(layout)
        self.controls_layout.addWidget(group)

    def _create_control_unit_group(self):
        group = QGroupBox("Control Unit")
        layout = QFormLayout()
        
        self.cu_input = QLineEdit()
        self.cu_input.setPlaceholderText("192.168.1.100")
        
        layout.addRow("Control Unit IP:", self.cu_input)
        group.setLayout(layout)
        self.controls_layout.addWidget(group)

    def _create_status_group(self):
        group = QGroupBox("Status Panel")
        layout = QFormLayout()
        
        self.status_label = QLabel("Disconnected")
        self.actual_fps_label = QLabel("0")
        self.incoming_res_label = QLabel("N/A")
        self.display_res_label = QLabel("N/A")
        self.error_label = QLabel("None")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: red;")

        layout.addRow("Status:", self.status_label)
        layout.addRow("Actual FPS:", self.actual_fps_label)
        layout.addRow("Incoming Res:", self.incoming_res_label)
        layout.addRow("Displayed Res:", self.display_res_label)
        layout.addRow("Last Error:", self.error_label)
        
        group.setLayout(layout)
        self.controls_layout.addWidget(group)

    def reset_ui_state(self):
        self.connect_btn.setText("Connect")
        self.video_label.clear()
        self.video_label.setText("Video Stream Disconnected")
        self.update_status_label("Disconnected", STATUS_DISCONNECTED_COLOR)
        self.update_resolution_label("N/A", "N/A")
        self.update_fps_label("0")

    def _connect_stream(self):
        rtsp_input = self.ip_input.text().strip()
        if not rtsp_input:
            self.reset_ui_state()
            self.update_error_label("IP Address is empty")
            return
        
        self.current_vt = VideoThread()
        self.current_vt.rtsp_url = rtsp_input
        self.current_vt.target_fps = int(self.fps) if self.fps else DEFAULT_FPS
        self.current_vt.vt_signal_update_image.connect(self.update_image)
        self.current_vt.vt_signal_update_fps_label.connect(self.update_fps_label)
        self.current_vt.vt_signal_update_resolution_label.connect(self.update_resolution_label)
        self.current_vt.vt_signal_update_status_label.connect(self.update_status_label)
        self.current_vt.vt_signal_update_error_label.connect(self.update_error_label)
        self.current_vt.vt_signal_reset_ui_state.connect(self.reset_ui_state)
        self.current_vt.vt_signal_disable_connect_button.connect(
            lambda: self.connect_btn.setEnabled(False)
        )
        self.current_vt.vt_signal_enable_connect_button.connect(
            lambda: self.connect_btn.setEnabled(True)
        )

        self.current_vt.vt_signal_connection_failed.connect(self.handle_connection_failure)
        self.current_vt.vt_signal_connection_retain.connect(self.handle_connection_retain)

        self.current_vt.start()
        self.connect_btn.setText("Disconnect")

    def _disconnect_stream(self):
        self.current_vt.stop()
        self.reset_ui_state()

    def toggle_connection(self):
        if self.current_vt and self.current_vt.isRunning():
            self._disconnect_stream()
        else:
            self._connect_stream()

    def update_image(self, cv_img):
        self.video_label.setPixmap(QPixmap.fromImage(cv_img))
    def update_status_label(self, msg, color):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")
    def update_error_label(self, err_msg):
        self.error_label.setText(err_msg)
    def update_resolution_label(self, incoming, displayed):
        self.incoming_res_label.setText(incoming)
        self.display_res_label.setText(displayed)
    def update_fps_label(self, fps_str):
        self.actual_fps_label.setText(fps_str)
        
    def update_fps(self):
        text = self.fps_input.text()
        if text.isdigit() and int(text) > 0:
            self.fps = int(text)
            if self.current_vt:
                self.current_vt.target_fps = self.fps

    def handle_connection_failure(self, msg):
        self.reset_ui_state()
        self.update_error_label(msg)

    def handle_connection_retain(self):
        # nothing to do for now
        pass

    def closeEvent(self, event):
        if self.current_vt:
            self.current_vt.stop()
        event.accept()

if __name__ == "__main__":

    cv2.setNumThreads(8)
    cv2.setUseOptimized(True)

    if not os.path.exists(MODEL_PATH):
        print(f"Error: Model file '{MODEL_PATH}' not found.")
        exit(1)
    model = load_model(MODEL_PATH)
    model.set_classes(classes if classes else [''])

    t = threading.Thread(target=input_thread, args=(command_queue,), daemon=True)
    t.start()

    app = QApplication(sys.argv)
    window = CameraApp()
    window.show()
    sys.exit(app.exec())
