import socket
import struct
import json
import time
import base64
import sys
import cv2
import numpy as np
from datetime import datetime

SERVER_IP = '127.0.0.1'
SERVER_PORT = 5000
DEVICE_IP = '192.168.1.101'

def send_json(sock, data_dict):
    try:
        json_bytes = json.dumps(data_dict).encode('utf-8')
        message = struct.pack('>I', len(json_bytes)) + json_bytes
        sock.sendall(message)
        return True
    except Exception as e:
        print(f"Send Error: {e}")
        return False

def recv_json(sock):
    header = recv_all(sock, 4)
    if not header: return None
    payload = recv_all(sock, struct.unpack('>I', header)[0])
    return json.loads(payload) if payload else None

def recv_all(sock, n):
    data = b''
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet: return None
        data += packet
    return data

def generate_image(text_overlay):
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    
    color = list(np.random.random(size=3) * 256)
    cv2.rectangle(img, (100, 100), (540, 380), color, -1)
    
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, f"Client: {DEVICE_IP}", (10, 50), font, 1, (255, 255, 255), 2)
    cv2.putText(img, f"Cmd: {text_overlay}", (10, 100), font, 1, (255, 255, 255), 2)
    cv2.putText(img, f"Time: {datetime.now()}", (10, 450), font, 0.7, (200, 200, 200), 1)
    
    _, buffer = cv2.imencode('.jpg', img)
    jpg_as_text = base64.b64encode(buffer).decode('utf-8')
    return jpg_as_text

def foo_cmd(command_text):
    print(f"Command received: {command_text}")

def foo_img():
    rets = []
    for _ in range(1):
        rets.append(generate_image('foo_img'))
    return rets

def send_image(img, sock):
    response = {
        "type": "response",
        "client_ip": DEVICE_IP,
        "timestamp": datetime.now().strftime("%Y-%m-%d_%H:%M:%S_%f"),
        "image": img
    }
    if not send_json(sock, response): return False
    # print("Response sent successfully.")
    return True

def rec_cmd_send_img(sock, cmd_handler_callback, img_getter_callback):
    last_img_time = 0
    while True:
        current_time = time.time()
        if current_time - last_img_time >= 1:
            imgs = img_getter_callback()
            for img in imgs:
                if not send_image(img, sock):
                    return
            last_img_time = current_time

        try:
            query : dict = recv_json(sock)
            if not query:
                print("Server closed connection.")
                return
        except (socket.timeout, TimeoutError):
            continue

        print(f"Received Query: {query}")
        if query.get('type') == 'query':
            command_text = query.get('command')
            # imgs = cmd_handler_callback(command_text)
            # for img in imgs:
            #     if not send_image(img, sock):
            #         return
            cmd_handler_callback(command_text)

def connect_to_server():
    print(f"Attempting connection to {SERVER_IP}:{SERVER_PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((SERVER_IP, SERVER_PORT))
    sock.settimeout(0.5)
    print(f"Connected to Server!")
    return sock

def run_client(cmd_handler_callback, img_getter_callback):
    running = True
    while running:
        try:
            sock : socket.socket = connect_to_server()
            rec_cmd_send_img(sock, cmd_handler_callback, img_getter_callback)
        except KeyboardInterrupt:
            print("Client shutting down.")
            sock.close()
            running = False
        except Exception as e:
            print(f"\033[91mConnection error: {e}\033[0m")
            continue
        finally:
            try: sock.close()
            except: pass
            if running:
                print("Reconnecting in 3 seconds...")
                time.sleep(3)

if __name__ == "__main__":
    run_client(foo_cmd, foo_img)
