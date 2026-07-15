import os
import subprocess
import tempfile
import sys
import time

from .interceptor import TelemetryClient

def _create_sitecustomize(mode, temp_dir):
    sitecustomize_path = os.path.join(temp_dir, "sitecustomize.py")
    script = f"""
import sys
import os

try:
    sys.path.remove(r"{temp_dir}")
except ValueError:
    pass

try:
    import h4_debug.interceptor
    h4_debug.interceptor.start_interception(mode="{mode}")
except ImportError as e:
    print(f"h4-debug: Failed to load interceptor: {{e}}", file=sys.stderr)
"""
    with open(sitecustomize_path, "w", encoding="utf-8") as f:
        f.write(script)

def handle_python(target, command, env, args):
    print(f"[h4-debug] Handling as Python script")
    temp_dir = tempfile.mkdtemp(prefix="h4_debug_")
    _create_sitecustomize(args.mode, temp_dir)
    
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{temp_dir}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = temp_dir
        
    env["H4_DEBUG_MODE"] = args.mode
    env["H4_DEBUG_PORT"] = str(args.port)

    print(f"[h4-debug] Launching process: {' '.join(command)}")
    process = None
    try:
        process = subprocess.Popen(command, env=env)
        process.wait()
    except KeyboardInterrupt:
        print("\n[h4-debug] Interrupted by user. Terminating process...")
        if process:
            process.terminate()
            process.wait()
    except Exception as e:
        print(f"[h4-debug] Error running command: {e}")

def handle_batch(target, command, env, args):
    print(f"[h4-debug] Handling as Batch script")
    client = TelemetryClient(args.port)
    time.sleep(0.5) # Wait for connection
    
    # Read batch file and send content
    try:
        with open(target, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            client.send("File", "batch_content", {"file": target, "content": content})
    except Exception as e:
        client.send("System", "error", {"text": f"Failed to read batch file: {e}"})

    # Prepare env for inner python calls
    temp_dir = tempfile.mkdtemp(prefix="h4_debug_")
    _create_sitecustomize(args.mode, temp_dir)
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{temp_dir}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = temp_dir
    env["H4_DEBUG_MODE"] = args.mode
    env["H4_DEBUG_PORT"] = str(args.port)
    
    print(f"[h4-debug] Launching batch process: {' '.join(command)}")
    process = None
    try:
        # Wrap command with cmd.exe /c if not already
        if not command[0].lower().endswith('cmd.exe'):
            cmd_args = ["cmd.exe", "/c"] + command
        else:
            cmd_args = command
            
        process = subprocess.Popen(cmd_args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        
        # Stream stdout and stderr
        import threading
        def stream_output(pipe, is_err):
            for line in pipe:
                client.send("Console", "stderr" if is_err else "stdout", {"text": line.rstrip()})
                print(line, end='', file=sys.stderr if is_err else sys.stdout)
                
        t1 = threading.Thread(target=stream_output, args=(process.stdout, False), daemon=True)
        t2 = threading.Thread(target=stream_output, args=(process.stderr, True), daemon=True)
        t1.start()
        t2.start()
        
        process.wait()
        t1.join()
        t2.join()
        
        client.send("System", "info", {"text": f"Batch process finished with code {process.returncode}"})
    except KeyboardInterrupt:
        print("\n[h4-debug] Interrupted by user.")
        if process:
            process.terminate()
            process.wait()
    except Exception as e:
        print(f"[h4-debug] Error running command: {e}")

def handle_image(target, command, env, args):
    print(f"[h4-debug] Handling as Image file")
    
    try:
        from PIL import Image
    except ImportError:
        print("[h4-debug] Pillow is not installed. EXIF extraction unavailable.")
        handle_generic(target, command, env, args)
        return

    def cmd_handler(cmd):
        if cmd.get("action") == "strip_exif":
            try:
                img = Image.open(target)
                data = list(img.getdata())
                image_without_exif = Image.new(img.mode, img.size)
                image_without_exif.putdata(data)
                
                name, ext = os.path.splitext(target)
                new_target = f"{name}_stripped{ext}"
                image_without_exif.save(new_target)
                client.send("System", "info", {"text": f"Image metadata stripped and saved to: {new_target}"})
                print(f"[h4-debug] Image stripped successfully: {new_target}")
            except Exception as e:
                client.send("System", "error", {"text": f"Failed to strip EXIF: {e}"})
            return True
        return False

    client = TelemetryClient(args.port, command_callback=cmd_handler)
    time.sleep(0.5)

    try:
        img = Image.open(target)
        exif = img.getexif()
        metadata = {
            "format": img.format,
            "mode": img.mode,
            "size": img.size,
            "exif": {k: str(v) for k, v in (exif.items() if exif else [])},
            "file": target
        }
        client.send("Data", "image_metadata", metadata)
        print(f"[h4-debug] Extracted metadata for {target}. Sent to dashboard.")
    except Exception as e:
        client.send("System", "error", {"text": f"Failed to read image metadata: {e}"})
        print(f"[h4-debug] Error reading image: {e}")
        
    print("[h4-debug] Image handler running. Dashboard is active. (Press Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[h4-debug] Exiting image handler.")

def handle_generic(target, command, env, args):
    print(f"[h4-debug] Handling as generic command")
    client = TelemetryClient(args.port)
    time.sleep(0.5)
    
    try:
        size = os.path.getsize(target)
        client.send("System", "info", {"text": f"Generic file: {target} (Size: {size} bytes)"})
    except Exception:
        pass

    process = None
    try:
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        
        import threading
        def stream_output(pipe, is_err):
            for line in pipe:
                client.send("Console", "stderr" if is_err else "stdout", {"text": line.rstrip()})
                print(line, end='', file=sys.stderr if is_err else sys.stdout)
                
        t1 = threading.Thread(target=stream_output, args=(process.stdout, False), daemon=True)
        t2 = threading.Thread(target=stream_output, args=(process.stderr, True), daemon=True)
        t1.start()
        t2.start()
        
        process.wait()
        t1.join()
        t2.join()
        
        client.send("System", "info", {"text": f"Generic process finished with code {process.returncode}"})
    except KeyboardInterrupt:
        if process:
            process.terminate()
            process.wait()
    except Exception as e:
        print(f"[h4-debug] Error running generic command: {e}")

def handle_node(target, command, env, args):
    print(f"[h4-debug] Handling as Node.js script")
    
    # Locate the interceptor script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    interceptor_path = os.path.join(current_dir, "node_interceptor.js").replace("\\", "/")
    
    # Format NODE_OPTIONS
    node_opts = env.get("NODE_OPTIONS", "")
    new_opt = f'--require "{interceptor_path}"'
    env["NODE_OPTIONS"] = f"{new_opt} {node_opts}".strip()
    
    env["H4_DEBUG_MODE"] = args.mode
    env["H4_DEBUG_PORT"] = str(args.port)
    
    process = None
    try:
        # If target is .js but command doesn't start with node, prepend node
        if target.endswith('.js') and command[0] == target:
            command = ["node"] + command
            
        process = subprocess.Popen(command, env=env)
        process.wait()
    except KeyboardInterrupt:
        if process:
            process.terminate()
            process.wait()
    except Exception as e:
        print(f"[h4-debug] Error running node command: {e}")

def handle_exe(target, command, env, args):
    print(f"[h4-debug] Handling as Native Executable (using ctypes Windows Debugger)")
    client = TelemetryClient(args.port)
    time.sleep(0.5)

    env["H4_DEBUG_MODE"] = args.mode
    env["H4_DEBUG_PORT"] = str(args.port)
    
    try:
        from h4_debug.win_debugger import debug_process
        client.send("System", "info", {"text": f"Starting native debug wrapper for {target}"})
        debug_process(command, client)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[h4-debug] Error running EXE command: {e}")

