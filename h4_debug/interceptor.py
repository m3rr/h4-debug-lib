import builtins
import json
import os
import queue
import socket
import json
import time
import traceback
import select
import sys
import threading
import sysconfig
from datetime import datetime

# We must keep references to original functions to avoid infinite recursion
_original_open = builtins.open
_original_socket = socket.socket
_original_print = builtins.print

class TelemetryClient:
    def __init__(self, port, command_callback=None):
        self.port = port
        self.command_callback = command_callback
        self.queue = queue.Queue()
        self.buffer = ""
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        # Connect to the local TCP server spawned by h4-debug
        server_port = self.port + 1
        
        while True:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as conn:
                    conn.connect(("127.0.0.1", server_port))
                    
                    while True:
                        # 1. Send all queued outgoing telemetry
                        while not self.queue.empty():
                            try:
                                msg = self.queue.get_nowait()
                                conn.sendall((json.dumps(msg) + "\n").encode("utf-8"))
                            except queue.Empty:
                                break
                                
                        # 2. Process incoming commands
                        r, _, _ = select.select([conn], [], [], 0.05)
                        if r:
                            data = conn.recv(4096)
                            if not data:
                                break # Connection closed
                                
                            self.buffer += data.decode("utf-8", errors="replace")
                            while "\n" in self.buffer:
                                line, self.buffer = self.buffer.split("\n", 1)
                                if line.strip():
                                    self._handle_command(line.strip())
                                    
                        time.sleep(0.01)
            except Exception:
                time.sleep(1)
                
    def _handle_command(self, cmd_data):
        try:
            cmd = json.loads(cmd_data)
            
            if self.command_callback and self.command_callback(cmd):
                return
                
            if cmd.get("action") == "set_mode":
                global _mode
                _mode = cmd.get("mode", "Normal")
                self.send("System", "info", {"text": f"Mode changed to {_mode}"})
                
            elif cmd.get("action") == "evaluate":
                code = cmd.get("code", "")
                result = None
                is_error = False
                
                # Try eval first, then exec
                try:
                    result = eval(code, globals())
                except SyntaxError:
                    try:
                        # Capture stdout for exec
                        import io
                        old_stdout = sys.stdout
                        sys.stdout = capture = io.StringIO()
                        exec(code, globals())
                        sys.stdout = old_stdout
                        result = capture.getvalue()
                    except Exception as e:
                        is_error = True
                        result = traceback.format_exc()
                except Exception as e:
                    is_error = True
                    result = traceback.format_exc()
                
                self.send("Console", "eval_result", {
                    "code": code,
                    "result": str(result),
                    "is_error": is_error
                })
        except Exception:
            pass

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

def is_user_code_path(filename):
    # Check if a filename belongs to the user's project
    cwd = os.getcwd()
    if filename.startswith(cwd):
        return True
    
    if "site-packages" in filename:
        return False
        
    stdlib = sysconfig.get_path('stdlib')
    if stdlib and filename.startswith(stdlib):
        return False
        
    # As a fallback, check if it starts with the python prefix
    if filename.startswith(sys.prefix) or filename.startswith(sys.base_prefix):
        return False
        
    return True

def trace_calls(frame, event, arg):
    global _mode
    if _mode == "Normal":
        return trace_calls # Always trace so we can hot-swap, but do nothing in Normal
        
    if not _telemetry:
        return trace_calls
        
    filename = frame.f_code.co_filename
    if "h4_debug" in filename or "websockets" in filename:
        return trace_calls # Ignore our own debugger code

    is_user_code = is_user_code_path(filename)
    
    if _mode == "Trace":
        if not is_user_code:
            return trace_calls
            
        if event == "call":
            _telemetry.send("Execution", "call", {
                "function": frame.f_code.co_name,
                "file": filename,
                "line": frame.f_lineno
            })
        elif event == "exception":
            exc_type, exc_value, _ = arg
            _telemetry.send("Execution", "exception", {
                "type": exc_type.__name__,
                "value": str(exc_value),
                "file": filename,
                "line": frame.f_lineno
            })
            
    elif _mode == "Full":
        if event == "line" and is_user_code:
            _telemetry.send("Execution", "line", {
                "function": frame.f_code.co_name,
                "file": filename,
                "line": frame.f_lineno
            })
        elif event in ("call", "return"):
            _telemetry.send("Execution", event, {
                "function": frame.f_code.co_name,
                "file": filename,
                "line": frame.f_lineno
            })
        elif event == "exception":
            exc_type, exc_value, _ = arg
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
    
    # Always engage tracing on startup so we can hot-swap modes dynamically
    # It will remain dormant if mode == "Normal"
    sys.settrace(trace_calls)
    threading.settrace(trace_calls)
    
    apply_patches()

def apply_patches():
    # Patch Disk
    builtins.open = patched_open
    
    # Patch Network
    socket.socket = PatchedSocket
    
    # Patch Console
    sys.stdout = PatchedStream(sys.stdout, "stdout")
    sys.stderr = PatchedStream(sys.stderr, "stderr")
        
    _telemetry.send("System", "init", {
        "mode": _mode,
        "pid": os.getpid(),
        "language": "python",
        "version": sys.version
    })
