import argparse
import os
import sys
import threading
import time
import webbrowser

from . import server
from . import handlers

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
    if command[0] == "--":
        command = command[1:]

    target = command[0]

    # 1. Start the web server in a background thread
    print(f"[h4-debug] Starting dashboard on http://localhost:{args.port} ...")
    server_thread = threading.Thread(target=server.run_server, args=(args.port,), daemon=True)
    server_thread.start()

    time.sleep(1.0)
    webbrowser.open(f"http://localhost:{args.port}")

    # 2. Setup interception environment
    env = os.environ.copy()

    # 3. Dispatch to handler based on file extension
    ext = ""
    if os.path.isfile(target):
        ext = os.path.splitext(target)[1].lower()

    if ext == ".py":
        handlers.handle_python(target, command, env, args)
    elif ext in [".bat", ".cmd"]:
        handlers.handle_batch(target, command, env, args)
    elif ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"]:
        handlers.handle_image(target, command, env, args)
    elif ext in [".js", ".ts", ".mjs", ".cjs"] or target.lower() in ["node", "npm", "npx", "node.exe", "npm.cmd", "npx.cmd"]:
        handlers.handle_node(target, command, env, args)
    elif ext == ".exe":
        handlers.handle_exe(target, command, env, args)
    else:
        # Check if it's implicitly a python script via "python script.py"
        if target.lower().endswith("python") or target.lower().endswith("python.exe"):
            handlers.handle_python(target, command, env, args)
        else:
            handlers.handle_generic(target, command, env, args)

    print("[h4-debug] Process finished. Dashboard will remain open until you exit (Ctrl+C).")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[h4-debug] Shutting down.")

if __name__ == "__main__":
    main()

