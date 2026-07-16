import asyncio
import json
import os
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Store connected dashboard clients and the active telemetry process
dashboard_clients: list[WebSocket] = []
telemetry_clients = set()
MAX_HISTORY = 1000

# For broadcasting logs to WebSockets
def broadcast_log(log_item_str):
    try:
        log_item = json.loads(log_item_str)
        log_history.append(log_item)
        if len(log_history) > MAX_HISTORY:
            log_history.pop(0)
    except Exception:
        pass
        
    disconnected_clients = []
    # Needs to be scheduled on the asyncio loop
    async def _send(client):
        try:
            await client.send_text(log_item_str)
        except Exception:
            disconnected_clients.append(client)
            
    for client in dashboard_clients.copy():
        asyncio.run_coroutine_threadsafe(_send(client), loop)
        
    for client in disconnected_clients:
        if client in dashboard_clients:
            dashboard_clients.remove(client)

# To persist logs for when a dashboard connects slightly after startup
log_history = []

# Get the path to static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def get_dashboard():
    dashboard_path = os.path.join(STATIC_DIR, "dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Dashboard not found</h1>")

@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """Endpoint for the web dashboard to receive logs and send commands."""
    await websocket.accept()
    
    # Send history on connect
    for log_item in log_history:
        try:
            await websocket.send_text(json.dumps(log_item))
        except Exception:
            break
            
    dashboard_clients.append(websocket)
    try:
        while True:
            # Receive commands from dashboard
            data = await websocket.receive_text()
            cmd = json.loads(data)
            
            if cmd.get("action") == "clear":
                log_history.clear()
            elif cmd.get("action") in ["evaluate", "set_mode"]:
                # Forward commands to ALL active telemetry processes via TCP
                dead_clients = set()
                for client in telemetry_clients:
                    try:
                        client.sendall((json.dumps(cmd) + "\n").encode("utf-8"))
                    except Exception:
                        dead_clients.add(client)
                        
                for dead in dead_clients:
                    telemetry_clients.discard(dead)

    except WebSocketDisconnect:
        if websocket in dashboard_clients:
            dashboard_clients.remove(websocket)

import socket
import threading

def run_tcp_server(port: int):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port + 1))
    server.listen(1)
    
    while True:
        conn, addr = server.accept()
        
        def handle_client(c):
            f = c.makefile("r", encoding="utf-8")
            telemetry_clients.add(c)
            try:
                while True:
                    line = f.readline()
                    if not line:
                        break
                    broadcast_log(line)
            except Exception:
                pass
            finally:
                if c in telemetry_clients:
                    telemetry_clients.remove(c)
                c.close()
                
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

def run_server(port: int):
    # Disable uvicorn access logs to keep terminal clean
    import logging
    log = logging.getLogger("uvicorn.access")
    log.setLevel(logging.WARNING)
    
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    threading.Thread(target=run_tcp_server, args=(port,), daemon=True).start()
    
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", loop="asyncio")
    server = uvicorn.Server(config)
    loop.run_until_complete(server.serve())
