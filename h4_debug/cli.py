import argparse
import os
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
import pathlib

from . import server

def create_sitecustomize(mode):
    temp_dir = tempfile.mkdtemp(prefix="h4_debug_")
    sitecustomize_path = os.path.join(temp_dir, "sitecustomize.py")
    
    # We will write a sitecustomize.py that imports our interceptor
    # and initializes it with the selected mode.
    script = f"""
import sys
import os

# Remove this temp dir from sys.path so we don't mess with other imports too much
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
    
    return temp_dir

def main():
    parser = argparse.ArgumentParser(description="h4-debug: Advanced application proxy debugger", usage="h4-debug [--mode MODE] command ...")
    parser.add_argument("--mode", choices=["Normal", "Trace", "Full"], default="Normal", help="Debugging mode")
    parser.add_argument("--port", type=int, default=8008, help="Port for the web dashboard")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    command = args.command
    # argparse puts '--' in the remainder if it's there
    if command[0] == "--":
        command = command[1:]

    # 1. Start the web server in a background thread
    print(f"[h4-debug] Starting dashboard on http://localhost:{args.port} ...")
    server_thread = threading.Thread(target=server.run_server, args=(args.port,), daemon=True)
    server_thread.start()

    # Give server a moment to start
    time.sleep(1.0)
    
    # Open dashboard in browser
    webbrowser.open(f"http://localhost:{args.port}")

    # 2. Setup interception environment
    env = os.environ.copy()
    
    # Python interception via sitecustomize
    sitecustomize_dir = create_sitecustomize(args.mode)
    
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = f"{sitecustomize_dir}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env["PYTHONPATH"] = sitecustomize_dir
        
    env["H4_DEBUG_MODE"] = args.mode
    env["H4_DEBUG_PORT"] = str(args.port)

    # 3. Launch the target process
    print(f"[h4-debug] Launching process: {' '.join(command)}")
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
    finally:
        print("[h4-debug] Process finished. Dashboard will remain open until you exit (Ctrl+C).")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("[h4-debug] Shutting down.")

if __name__ == "__main__":
    main()
