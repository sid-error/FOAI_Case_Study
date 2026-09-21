from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
import json
import uuid
import asyncio
import time

# Initialize the FastAPI application
app = FastAPI(title="Smart Elevator Central Manager")

# Configure CORS to allow cross-origin requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global metrics and state tracking variables
active_auctions: Dict[str, List[dict]] = {}
request_times: Dict[str, float] = {}  
total_wait_time = 0.0
completed_requests = 0

class ConnectionManager:
    """Manages active WebSocket connections for both elevators and frontend clients."""
    def __init__(self):
        self.active_elevators: List[WebSocket] = []
        self.frontend_clients: List[WebSocket] = []

    async def connect_elevator(self, websocket: WebSocket):
        await websocket.accept()
        self.active_elevators.append(websocket)

    async def connect_frontend(self, websocket: WebSocket):
        await websocket.accept()
        self.frontend_clients.append(websocket)

    def disconnect_elevator(self, websocket: WebSocket):
        if websocket in self.active_elevators:
            self.active_elevators.remove(websocket)

    def disconnect_frontend(self, websocket: WebSocket):
        if websocket in self.frontend_clients:
            self.frontend_clients.remove(websocket)

    async def broadcast_to_elevators(self, payload: dict):
        for connection in self.active_elevators:
            await connection.send_json(payload)

    async def broadcast_to_frontend(self, payload: dict):
        for connection in self.frontend_clients:
            await connection.send_json(payload)

manager = ConnectionManager()

async def resolve_auction(request_id: str):
    """
    Resolve a bidding auction by assigning the task to the elevator 
    with the lowest bid cost. Handles edge cases like all elevators broken.
    """
    bids = active_auctions.get(request_id, [])
    if not bids:
        return
    
    winning_bid = min(bids, key=lambda x: x["cost"])
    
    if winning_bid["cost"] >= 999999:
        await manager.broadcast_to_frontend({
            "type": "LOG", 
            "message": f"CRITICAL: Request {request_id} failed. No active elevators."
        })
        del active_auctions[request_id]
        return

    winner_ws = winning_bid["ws"]
    await winner_ws.send_json({
        "type": "TASK_ASSIGNED",
        "request_id": request_id
    })
    
    del active_auctions[request_id]

# --- WebSocket Endpoints ---

@app.websocket("/ws/frontend")
async def frontend_endpoint(websocket: WebSocket):
    """WebSocket endpoint for the frontend UI to receive state updates and logs."""
    await manager.connect_frontend(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_frontend(websocket)

@app.websocket("/ws/elevator/{elevator_id}")
async def elevator_endpoint(websocket: WebSocket, elevator_id: int):
    """WebSocket endpoint for elevator agents to connect, bid on tasks, and send updates."""
    await manager.connect_elevator(websocket)
    global total_wait_time, completed_requests
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "BID":
                req_id = data["request_id"]
                if req_id not in active_auctions:
                    active_auctions[req_id] = []
                    
                active_auctions[req_id].append({
                    "elevator_id": elevator_id, 
                    "cost": data["bid_cost"], 
                    "ws": websocket
                })
                
                if len(active_auctions[req_id]) == len(manager.active_elevators):
                    await resolve_auction(req_id)
                    
            elif data.get("type") == "STATE_UPDATE":
                await manager.broadcast_to_frontend(data)

            elif data.get("type") == "TASK_COMPLETED":
                req_id = data["request_id"]
                if req_id in request_times:
                    wait_time = round(time.time() - request_times[req_id], 2)
                    total_wait_time += wait_time
                    completed_requests += 1
                    
                    await manager.broadcast_to_frontend({
                        "type": "METRICS_UPDATE",
                        "completed": completed_requests,
                        "avg_wait": round((total_wait_time / completed_requests), 2)
                    })
                    
                    await manager.broadcast_to_frontend({
                        "type": "LOG",
                        "message": f"Request {req_id} completed (Wait: {wait_time}s)"
                    })

    except WebSocketDisconnect:
        manager.disconnect_elevator(websocket)

# --- HTTP Endpoints ---

@app.post("/request_elevator")
async def request_elevator(pickup: int, dropoff: int):
    """REST endpoint to manually trigger a new elevator request and initiate an auction."""
    request_id = "REQ-" + str(uuid.uuid4())[:4].upper() 
    request_times[request_id] = time.time()
    
    await manager.broadcast_to_elevators({
        "type": "BID_REQUEST",
        "request_id": request_id,
        "pickup": pickup,
        "dropoff": dropoff
    })
    
    active_auctions[request_id] = []
    
    await manager.broadcast_to_frontend({
        "type": "LOG",
        "message": f"Broadcast: {request_id} (Floor {pickup} -> {dropoff})"
    })
    return {"message": "Auction started", "request_id": request_id}

@app.post("/reset")
async def reset_system():
    """REST endpoint to reset the system state, metrics, and connected elevator agents."""
    global total_wait_time, completed_requests, active_auctions, request_times
    total_wait_time = 0.0
    completed_requests = 0
    active_auctions.clear()
    request_times.clear()
    
    await manager.broadcast_to_elevators({"type": "RESET_AGENT"})
    await manager.broadcast_to_frontend({
        "type": "METRICS_UPDATE",
        "completed": 0,
        "avg_wait": 0.00
    })
    return {"message": "System reset fully"}

@app.post("/break/{elevator_id}")
async def break_elevator(elevator_id: int):
    """REST endpoint to simulate a critical failure in a specific elevator."""
    await manager.broadcast_to_elevators({
        "type": "STATUS_CHANGE",
        "target": elevator_id,
        "status": "BROKEN"
    })
    await manager.broadcast_to_frontend({
        "type": "LOG",
        "message": f"Elevator {elevator_id} encountered a critical failure."
    })
    return {"message": f"Elevator {elevator_id} broken"}

@app.post("/fix/{elevator_id}")
async def fix_elevator(elevator_id: int):
    """REST endpoint to repair a broken elevator and bring it back online."""
    await manager.broadcast_to_elevators({
        "type": "STATUS_CHANGE",
        "target": elevator_id,
        "status": "ACTIVE"
    })
    await manager.broadcast_to_frontend({
        "type": "LOG",
        "message": f"Elevator {elevator_id} has been repaired and is online."
    })
    return {"message": f"Elevator {elevator_id} fixed"}