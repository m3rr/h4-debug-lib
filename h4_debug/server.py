import asyncio
import json
import os
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Store connected dashboard clients and the active telemetry process
dashboard_clients = []
active_telemetry_client = None

# To persist logs for when a dashboard connects slightly after startup
log_history = []
MAX_HISTORY = 5000

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

@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """Endpoint for the intercepted process to push logs and receive commands."""
    global active_telemetry_client
    await websocket.accept()
    active_telemetry_client = websocket
    
    try:
        while True:
            data = await websocket.receive_text()
            
            try:
                log_item = json.loads(data)
                log_history.append(log_item)
                if len(log_history) > MAX_HISTORY:
                    log_history.pop(0)
            except Exception:
                pass
                
            # Broadcast to all dashboards
            disconnected_clients = []
            for client in dashboard_clients:
                try:
                    await client.send_text(data)
                except Exception:
                    disconnected_clients.append(client)
            
            for client in disconnected_clients:
                if client in dashboard_clients:
                    dashboard_clients.remove(client)
    except WebSocketDisconnect:
        if active_telemetry_client == websocket:
            active_telemetry_client = None

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
                # Forward commands to the active telemetry process
                if active_telemetry_client:
                    try:
                        await active_telemetry_client.send_text(json.dumps(cmd))
                    except Exception:
                        pass
    except WebSocketDisconnect:
        if websocket in dashboard_clients:
            dashboard_clients.remove(websocket)

def run_server(port: int):
    # Disable uvicorn access logs to keep terminal clean
    import logging
    log = logging.getLogger("uvicorn.access")
    log.setLevel(logging.WARNING)
    
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
