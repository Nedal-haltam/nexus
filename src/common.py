import os
import socket
import struct
import json
import threading
import time
import base64
import sys
import torch
import cv2
import queue
import numpy as np

from datetime import datetime
from ultralytics import YOLO
from PySide6.QtCore import Qt, Signal, QObject, Slot, QTimer, QThread
from PySide6.QtGui import QImage, QPixmap, QTextCursor, QColor, QIntValidator
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                               QListWidget, QTextEdit, QSplitter, QGroupBox, 
                               QMessageBox, QListWidgetItem, QMenu, QCheckBox, QFormLayout)


NEXUS_DISPLAY_WIDTH = 640
NEXUS_DISPLAY_HEIGHT = 480
NEXUS_INFERENCE_WIDTH = NEXUS_DISPLAY_WIDTH#320
NEXUS_INFERENCE_HEIGHT = NEXUS_DISPLAY_HEIGHT#256

NEXUS_DEFAULT_FPS = 30
# DETECTION_SKIP_FRAMES = 30
STATUS_CONNECTING_COLOR = "blue"
STATUS_CONNECTED_COLOR = "green"
STATUS_DISCONNECTED_COLOR = "orange"
STATUS_ERROR_COLOR = "red"
NEXUS_CAMERA_AUTO_RECONNECT = True

MODEL_PATH = "./models/yolov8s-world.pt"
# MODEL_PATH = "./models/yolov8s-worldv2.pt"
# MODEL_PATH = "./models/yolov8m-worldv2.pt"
INFERENCE_DEVICE = 'cpu'
VIDEO_CAPTURE_TIMEOUT_MS = 5000
POST_CAMERA_RECONNECT_WAIT_ITERATIONS = 20
POST_CAMERA_RECONNECT_WAIT_INTERVAL = 0.1

CS_JSON_PROTOCOL_HEADER_SIZE = 4
C2S_CONNECTION_TIMEOUT = 5

SERVER_SYS_LOG_MAX_SIZE = 1024
SERVER_SYS_LOG_DELETE_LOG_SIZE = 512
SERVER_PORT = 5000
SERVER_BACKLOG = 128
SENT_COMMAND_HISTORY_SIZE_LIMIT = 10
SERVER_NOTIFY_SOUND_COOLDOWN_SECONDS = 5

CLIENT_DEVICE_IP = '192.168.1.101/dummy'
CLIENT_RECEIVE_TIMEOUT = 0.5
CLIENT_SEND_MESSAGE_INTERVAL = 1.0
