import socket
import json
import time
import threading
import queue
from slm_server import SLM_server

SERVER_IP = '192.168.1.102'
SERVER_PORT = 5000
BUFFER_SIZE = 1024

REINIT_INTERVAL_SEC = 3600          # reinitialize period
MIN_IDLE_BEFORE_REINIT_SEC = 200     # idle time
CMD_QUEUE_MAXSIZE = 256

slmtest = SLM_server()
cmd_q = queue.Queue(maxsize=CMD_QUEUE_MAXSIZE)

# Periodic self-reinit enable/disable (default: enabled)
self_reinit_enabled = threading.Event()
self_reinit_enabled.set()  # True => periodic reinit allowed

default_pattern = {
    "dimension": 0,
    "phase": 0.0,
    "center_x": 960,
    "center_y": 600,
    "grating_spacing": 10,
    "angle_deg": 0,
    "mask": 1  # 1=spot, 2=grating
}
last_pattern = {
    "dimension": 0,
    "phase": 0.0,
    "center_x": 960,
    "center_y": 600,
    "grating_spacing": 10,
    "angle_deg": 0,
    "mask": 1
}

_last_activity_lock = threading.Lock()
_last_activity_monotonic = time.monotonic()

def _touch_activity():
    global _last_activity_monotonic
    with _last_activity_lock:
        _last_activity_monotonic = time.monotonic()

def _seconds_since_last_activity():
    with _last_activity_lock:
        return time.monotonic() - _last_activity_monotonic

def slm_worker():
    try:
        print("Initializing SLM...")
        slmtest.initialize_slm()
        _apply_pattern(last_pattern, fast=True)
        _touch_activity()
    except Exception as e:
        print(f"Error during initial init: {e}")

    while True:
        task = cmd_q.get()
        if task is None:
            break

        ttype = task.get("type")
        try:
            if ttype == "REINIT":
                print("Reinitializing SLM...")
                slmtest.initialize_slm()
                print("Reinit done.")

            elif ttype == "APPLY":
                last_pattern.update({
                    "dimension": task["dimension"],
                    "phase": task["phase"],
                    "center_x": task["center_x"],
                    "center_y": task["center_y"],
                    "grating_spacing": task["grating_spacing"],
                    "angle_deg": task["angle_deg"],
                    "mask": task["mask"]
                })
                _apply_pattern(last_pattern, fast=True)
                _touch_activity()

            else:
                print(f"Unknown task type: {ttype}")
        except Exception as e:
            print(f"Error handling task {ttype}: {e}")
        finally:
            cmd_q.task_done()

def _apply_pattern(pat, fast=True):
    img = slmtest.generate_mask(
        dimension=pat["dimension"],
        phase=pat["phase"],
        center_x=pat["center_x"],
        center_y=pat["center_y"],
        grating_spacing=pat["grating_spacing"],
        angle_deg=pat["angle_deg"],
        mask=pat["mask"]
    )
    if fast:
        slmtest.fast_upload_to_slm(img)
    else:
        slmtest.upload_to_slm(img)

    print(
        f'-> mask: {slmtest.mask_type}, '
        f'dimension={pat["dimension"]} um, '
        f'phase={pat["phase"]} pi, '
        f'center=({pat["center_x"]},{pat["center_y"]}), '
        f'spacing={pat["grating_spacing"]}, angle={pat["angle_deg"]}'
    )
    print('Waiting for next task...\n')

def periodic_reinit_scheduler():
    next_tick = time.monotonic() + REINIT_INTERVAL_SEC
    while True:
        time.sleep(0.5)
        if not self_reinit_enabled.is_set():
            continue  

        now = time.monotonic()
        if now < next_tick:
            continue

        next_tick += REINIT_INTERVAL_SEC

        idle_secs = _seconds_since_last_activity()
        if idle_secs < MIN_IDLE_BEFORE_REINIT_SEC:
            print(f"Skipped: only idle {idle_secs:.1f}s (need {MIN_IDLE_BEFORE_REINIT_SEC}s).\n")
            continue

        if not cmd_q.empty():
            print("Skipped: command queue not empty.")
            continue

        try:
            cmd_q.put_nowait({"type": "REINIT"})
            print("Enqueued REINIT (idle & queue empty).")
        except queue.Full:
            print("Skipped: queue full.")

def start_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((SERVER_IP, SERVER_PORT))
        server_socket.listen(1)
        print(f'Server listening on {SERVER_IP}:{SERVER_PORT}...')

        while True:
            conn, addr = server_socket.accept()
            print(f'Connected by {addr}')
            handle_client(conn)

def handle_client(conn):
    with conn:
        while True:
            try:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    print("Client disconnected.")
                    break

                command = data.decode('utf-8').strip()
                print(f"Received command: {command}")

                parsed = analyze_command(command)
                if parsed is None:
                    print("Ignoring malformed command.")
                    continue

                (dimension, phase, center_x, center_y,
                 grating_spacing, angle_deg, mask, init_flag) = parsed

                if init_flag is True:
                    self_reinit_enabled.clear()
                    enqueue_reinit_then_apply(
                        dimension, phase, center_x, center_y, grating_spacing, angle_deg, mask
                    )
                else:
                    self_reinit_enabled.set()
                    enqueue_apply_only(
                        dimension, phase, center_x, center_y, grating_spacing, angle_deg, mask
                    )

            except ConnectionResetError:
                print("SLM_find_spot.py disconnected")
                break
            except Exception as e:
                print(f"Error while handling client: {e}")
                break

def enqueue_apply_only(dimension, phase, center_x, center_y, grating_spacing, angle_deg, mask):
    task = {
        "type": "APPLY",
        "dimension": dimension,
        "phase": phase,
        "center_x": center_x,
        "center_y": center_y,
        "grating_spacing": grating_spacing,
        "angle_deg": angle_deg,
        "mask": mask
    }
    try:
        cmd_q.put_nowait(task)
    except queue.Full:
        try:
            _ = cmd_q.get_nowait()
            cmd_q.task_done()
            cmd_q.put_nowait(task)
            print("Queue full: dropped one stale task to enqueue latest APPLY.")
        except Exception as e:
            print(f"Failed to enqueue APPLY: {e}")

def enqueue_reinit_then_apply(dimension, phase, center_x, center_y, grating_spacing, angle_deg, mask):
    try:
        cmd_q.put_nowait({"type": "REINIT"})
        cmd_q.put_nowait({
            "type": "APPLY",
            "dimension": dimension,
            "phase": phase,
            "center_x": center_x,
            "center_y": center_y,
            "grating_spacing": grating_spacing,
            "angle_deg": angle_deg,
            "mask": mask
        })
    except queue.Full:
        freed = 0
        try:
            _ = cmd_q.get_nowait(); cmd_q.task_done(); freed += 1
            _ = cmd_q.get_nowait(); cmd_q.task_done(); freed += 1
        except Exception:
            pass
        try:
            cmd_q.put_nowait({"type": "REINIT"})
            cmd_q.put_nowait({
                "type": "APPLY",
                "dimension": dimension,
                "phase": phase,
                "center_x": center_x,
                "center_y": center_y,
                "grating_spacing": grating_spacing,
                "angle_deg": angle_deg,
                "mask": mask
            })
            print(f"Queue full: dropped {freed} task(s) to enqueue REINIT+APPLY.")
        except Exception as e:
            print(f"Failed to enqueue REINIT+APPLY: {e}")

def analyze_command(command):
    """
    Returns: (dimension, phase, center_x, center_y, grating_spacing, angle_deg, mask, init_flag)
    init_flag is True/False; default False if missing.
    """
    # Defaults
    dimension = 0
    phase = 0.0
    center_x = 1920 // 2
    center_y = 1200 // 2
    mask = 1  # 1=spot, 2=grating
    grating_spacing = 10
    angle_deg = 0
    init_flag = False  # default if missing

    try:
        d = json.loads(command)

        # initialize
        init_flag = bool(d.get("initialize", False))

        m = d.get("mask", "spot")
        cx, cy = d.get("center", [center_x, center_y])
        center_x, center_y = int(cx), int(cy)
        dimension = int(d.get("dimension", dimension))
        phase = float(d.get("phase", phase))
        grating_spacing = int(d.get("spacing", grating_spacing))
        angle_val = d.get("angle", d.get("angle_deg", angle_deg))

        angle_deg = float(angle_val) if isinstance(angle_val, (int, float, str)) else angle_deg
        angle_deg = float(angle_deg)

        if m == "spot":
            mask = 1
            print("Mask: spot")
        elif m == "grating":
            mask = 2
            print("Mask: grating")
        else:
            print("Unknown mask; set to default spot.")
            mask = 1

        return (dimension, phase, center_x, center_y, grating_spacing, angle_deg, mask, init_flag)

    except json.JSONDecodeError:
        parts = command.split()
        if len(parts) == 3:
            try:
                dimension = int(parts[0])
                phase = float(parts[1])
                mask = int(parts[2])
                return (dimension, phase, center_x, center_y, grating_spacing, angle_deg, mask, init_flag)
            except ValueError:
                print("Plaintext 3-arg parse failed.")
                return None

        elif len(parts) == 7:
            try:
                dimension = int(parts[0])
                phase = float(parts[1])
                center_x = int(parts[2])
                center_y = int(parts[3])
                grating_spacing = int(parts[4])
                angle_deg = float(parts[5])
                mask = int(parts[6])
                return (dimension, phase, center_x, center_y, grating_spacing, angle_deg, mask, init_flag)
            except ValueError:
                print("Plaintext 7-arg parse failed.")
                return None

        else:
            print("Wrong plaintext format length.")
            return None

if __name__ == '__main__':
    threading.Thread(target=slm_worker, daemon=True).start()
    threading.Thread(target=periodic_reinit_scheduler, daemon=True).start()
    start_server()
