from common import *

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
    header = recv_all(sock, CS_JSON_PROTOCOL_HEADER_SIZE)
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
    cv2.putText(img, f"Client: {CLIENT_DEVICE_IP}", (10, 50), font, 1, (255, 255, 255), 2)
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
        "client_ip": CLIENT_DEVICE_IP,
        "timestamp": datetime.now().strftime("%Y-%m-%d_%H:%M:%S_%f"),
        "image": img
    }
    if not send_json(sock, response): return False
    # print("Response sent successfully.")
    return True

def connect_to_server(server_ip, server_port):
    print(f"Attempting connection to {server_ip}:{server_port}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(C2S_CONNECTION_TIMEOUT)
    sock.connect((server_ip, int(server_port)))
    sock.settimeout(CLIENT_RECEIVE_TIMEOUT)
    print(f"Connected to Server!")
    return sock

stop_event = threading.Event()
def stop_client():
    stop_event.set()

def run_client(server_ip, server_port, cmd_handler_callback, img_getter_callback):
    try:
        stop_event.clear()
        sock : socket.socket = connect_to_server(server_ip, server_port)
        last_img_time = 0
        while not stop_event.is_set():
            current_time = time.time()
            if current_time - last_img_time >= CLIENT_SEND_MESSAGE_INTERVAL:
                imgs = img_getter_callback()
                for img in imgs:
                    if not send_image(img, sock): return
                last_img_time = current_time

            try:
                query : dict = recv_json(sock)
                if not query:
                    print("Server closed connection.")
                    return
            except (socket.timeout, TimeoutError):
                continue

            if query.get('type') == 'query':
                command_text = query.get('command')
                cmd_handler_callback(command_text)
    except Exception as e:
        print(f"\033[91mConnection error: {e}\033[0m")
    finally:
        try: sock.close()
        except: pass
