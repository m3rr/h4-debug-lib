import builtins
import json
import os
import queue
import socket
import sys
import threading
import time
import traceback
from datetime import datetime

try:
    from websockets.sync.client import connect
except ImportError:
    connect = None

# We must keep references to original functions to avoid infinite recursion
_original_open = builtins.open
_original_socket = socket.socket
_original_print = builtins.print

class TelemetryClient:
    def __init__(self, port):
        self.port = port
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        ws_url = f"ws://127.0.0.1:{self.port}/ws/telemetry"
        if not connect:
            return
            
        while True:
            try:
                # Use original socket context if websockets internally creates sockets
                # This might be tricky because websockets uses asyncio or sync wrappers 
                # which use the monkeypatched socket. We must be very careful.
                # A safer approach for the telemetry thread is to unpatch socket temporarily or 
                # ensure our hooks bypass if thread == telemetry_thread
                with connect(ws_url) as websocket:
                    while True:
                        msg = self.queue.get()
                        websocket.send(json.dumps(msg))
                        self.queue.task_done()
            except Exception as e:
                time.sleep(1)

    def send(self, module, event_type, data):
        msg = {
            "timestamp": datetime.now().isoformat(),
            "module": module,
            "type": event_type,
            "data": data,
            "thread": threading.current_thread().name
        }
        self.queue.put(msg)


_telemetry = None
_mode = "Normal"
_telemetry_thread_id = None

def _is_telemetry_thread():
    return threading.get_ident() == _telemetry_thread_id

# --- Disk Interception ---

def patched_open(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
    if not _is_telemetry_thread() and _telemetry:
        _telemetry.send("Disk", "open", {
            "file": str(file),
            "mode": mode
        })
    return _original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

# --- Network Interception ---

class PatchedSocket(_original_socket):
    def __init__(self, family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, fileno=None):
        super().__init__(family, type, proto, fileno)
        self._h4_peer = None

    def connect(self, address):
        if not _is_telemetry_thread() and _telemetry:
            self._h4_peer = address
            _telemetry.send("Network", "connect", {
                "address": str(address)
            })
        return super().connect(address)
        
    def send(self, data, flags=0):
        if not _is_telemetry_thread() and _telemetry:
            payload = data.hex() if _mode == "Full" else (data[:100].hex() + "..." if len(data)>100 else data.hex())
            # try to decode as text
            try:
                text_payload = data.decode('utf-8', errors='ignore')
            except Exception:
                text_payload = None
                
            _telemetry.send("Network", "send", {
                "address": str(self._h4_peer),
                "bytes": len(data),
                "payload_hex": payload,
                "payload_text": text_payload
            })
        return super().send(data, flags)
        
    def recv(self, bufsize, flags=0):
        data = super().recv(bufsize, flags)
        if not _is_telemetry_thread() and _telemetry:
            payload = data.hex() if _mode == "Full" else (data[:100].hex() + "..." if len(data)>100 else data.hex())
            try:
                text_payload = data.decode('utf-8', errors='ignore')
            except Exception:
                text_payload = None
                
            _telemetry.send("Network", "recv", {
                "address": str(self._h4_peer),
                "bytes": len(data),
                "payload_hex": payload,
                "payload_text": text_payload
            })
        return data

# --- Stdout/Stderr Interception ---

class PatchedStream:
    def __init__(self, original_stream, stream_name):
        self.original_stream = original_stream
        self.stream_name = stream_name

    def write(self, text):
        if not _is_telemetry_thread() and _telemetry and text.strip():
            _telemetry.send("Console", self.stream_name, {"text": text})
        return self.original_stream.write(text)

    def flush(self):
        return self.original_stream.flush()

    def __getattr__(self, name):
        return getattr(self.original_stream, name)


# --- Execution Tracing ---

def trace_calls(frame, event, arg):
    if _is_telemetry_thread() or not _telemetry:
        return trace_calls
        
    if event == "call":
        func_name = frame.f_code.co_name
        filename = frame.f_code.co_filename
        # Ignore our own files and standard library to avoid noise, unless Full Debug
        if "h4_debug" not in filename and ("site-packages" not in filename or _mode == "Full"):
            _telemetry.send("Execution", "call", {
                "function": func_name,
                "file": filename,
                "line": frame.f_lineno
            })
    elif event == "exception" and _mode in ("Trace", "Full"):
        exc_type, exc_value, exc_traceback = arg
        filename = frame.f_code.co_filename
        if "h4_debug" not in filename:
            _telemetry.send("Execution", "exception", {
                "type": exc_type.__name__,
                "value": str(exc_value),
                "file": filename,
                "line": frame.f_lineno
            })
            
    return trace_calls

def start_interception(mode="Normal"):
    global _telemetry, _mode, _telemetry_thread_id
    _mode = mode
    
    port = int(os.environ.get("H4_DEBUG_PORT", 8008))
    _telemetry = TelemetryClient(port)
    _telemetry_thread_id = _telemetry.thread.ident
    
    # Patch Disk
    builtins.open = patched_open
    
    # Patch Network
    socket.socket = PatchedSocket
    
    # Patch Console
    sys.stdout = PatchedStream(sys.stdout, "stdout")
    sys.stderr = PatchedStream(sys.stderr, "stderr")
    
    # Enable Tracing if required
    if mode in ("Trace", "Full"):
        sys.settrace(trace_calls)
        
    _telemetry.send("System", "init", {"mode": mode, "pid": os.getpid()})

