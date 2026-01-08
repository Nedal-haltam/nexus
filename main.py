import sys
import cv2
import time
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QGroupBox, QFormLayout)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QImage, QPixmap, QIntValidator

WIDTH = 640
HEIGHT = 480
DEFAULT_FPS = 25
STATUS_CONNECTING_COLOR = "blue"
STATUS_CONNECTED_COLOR = "green"
STATUS_DISCONNECTED_COLOR = "orange"
STATUS_ERROR_COLOR = "red"

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
    cap : cv2.VideoCapture = None

    def __init__(self):
        super().__init__()
        self._run_flag = True
        self.rtsp_url = ""
        self.target_fps = DEFAULT_FPS
        self.last_frame_time = 0
        self.incoming_width = 0
        self.incoming_height = 0

    def init(self) -> tuple[bool, str]:
        if not self.init_video_capture():
            return False, f"Failed to open {self.rtsp_url}"
        return True, ""

    def init_video_capture(self) -> bool:
        self.cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000
        ])
        if not self.cap.isOpened():
            return None
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
            time.sleep(2)
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

    def run(self):
        self.vt_signal_update_status_label.emit("Connecting...", STATUS_CONNECTING_COLOR)
        if not self.connect_to_camera():
            self.vt_signal_update_status_label.emit("Disconnected", STATUS_DISCONNECTED_COLOR)
            self.vt_signal_connection_failed.emit(f"Failed to open {self.rtsp_url}")
            return
        self.vt_signal_update_status_label.emit("Connected", STATUS_CONNECTED_COLOR)

        self.incoming_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.incoming_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        while self._run_flag:
            if not self.cap.isOpened() or not self.cap.grab():
                # self.vt_signal_update_status_label.emit("ReConnecting...", STATUS_CONNECTING_COLOR)
                self.vt_signal_update_error_label.emit("Stream lost")
                break
                # if not self.reconnect_to_camera():
                #     break
                # self.vt_signal_update_status_label.emit("Connected", STATUS_CONNECTED_COLOR)
                # continue
            current_time = time.time()
            time_diff = current_time - self.last_frame_time
            if time_diff >= (1.0 / self.target_fps):
                self.last_frame_time = current_time
                ret, cv_img = self.cap.retrieve()
                if not ret:
                    continue
                p = self.cvimage_to_qimage(cv_img)
                self.vt_signal_update_resolution_label.emit(self.incoming_res(), f"{p.width()}x{p.height()}")
                actual_fps = 1.0 / time_diff
                self.vt_signal_update_fps_label.emit(f"{actual_fps:.1f}")
                self.vt_signal_update_image.emit(p)

            self.vt_signal_connection_retain.emit()
        
        self.vt_signal_reset_ui_state.emit()
        self.cap.release()

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
        self.fps_input.setValidator(QIntValidator(1, 60))
        self.fps_input.setText("25")
        
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
    app = QApplication(sys.argv)
    window = CameraApp()
    window.show()
    sys.exit(app.exec())