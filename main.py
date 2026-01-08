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

