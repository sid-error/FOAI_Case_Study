from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import json
import uuid
import asyncio
import time
import redis.asyncio as redis
import os

app = FastAPI(title="Smart Elevator API Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
redis_client = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

class ConnectionManager:
    def __init__(self):
        self.frontend_clients: List[WebSocket] = []

    async def connect_frontend(self, websocket: WebSocket):
        await websocket.accept()
        self.frontend_clients.append(websocket)

    def disconnect_frontend(self, websocket: WebSocket):
        if websocket in self.frontend_clients:
            self.frontend_clients.remove(websocket)

    async def broadcast_to_frontend(self, payload: dict):
        # We need to handle disconnected clients
        disconnected = []
        for connection in self.frontend_clients:
            try:
                await connection.send_json(payload)
            except Exception:
                disconnected.append(connection)
        for d in disconnected:
            self.disconnect_frontend(d)

manager = ConnectionManager()

# Global metrics
request_times = {}
total_wait_time = 0.0
completed_requests = 0

async def redis_listener():
    """Background task to listen to Redis and forward to frontend."""
    pubsub = redis_client.pubsub()
    await pubsub.subscribe("elevator_network", "elevator_logs")
    global total_wait_time, completed_requests
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            channel = message["channel"]
            try:
                data = json.loads(message["data"])
                
                if channel == "elevator_logs":
                    await manager.broadcast_to_frontend({
                        "type": "LOG",
                        "message": data["message"]
                    })
                
                elif channel == "elevator_network":
                    msg_type = data.get("type")
                    if msg_type == "STATE_UPDATE":
                        await manager.broadcast_to_frontend(data)
                    elif msg_type == "TASK_COMPLETED":
                        req_id = data.get("request_id")
                        if req_id in request_times:
                            wait_time = round(time.time() - request_times[req_id], 2)
                            total_wait_time += wait_time
                            completed_requests += 1
                            
                            await manager.broadcast_to_frontend({
                                "type": "METRICS_UPDATE",
                                "completed": completed_requests,
                                "avg_wait": round((total_wait_time / completed_requests), 2)
                            })
            except Exception as e:
                print(f"Error processing redis message: {e}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(redis_listener())

@app.websocket("/ws/frontend")
async def frontend_endpoint(websocket: WebSocket):
    await manager.connect_frontend(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_frontend(websocket)

@app.post("/request_elevator")
async def request_elevator(pickup: int, dropoff: int, people: int = 1):
    request_id = "REQ-" + str(uuid.uuid4())[:4].upper() 
    request_times[request_id] = time.time()
    
    # Publish to Redis instead of managing auction
    await redis_client.publish("elevator_network", json.dumps({
        "type": "BID_REQUEST",
        "request_id": request_id,
        "pickup": pickup,
        "dropoff": dropoff,
        "people": people
    }))
    
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_str = f"[{timestamp}] [API_GATEWAY] -> [BROADCAST] | BID_REQUEST: {{\"request_id\": \"{request_id}\", \"pickup\": {pickup}, \"dropoff\": {dropoff}, \"people\": {people}}}"
    print(log_str, flush=True)
    await redis_client.publish("elevator_logs", json.dumps({"message": log_str}))
    
    return {"message": "Request broadcasted", "request_id": request_id}

@app.post("/reset")
async def reset_system():
    global total_wait_time, completed_requests, request_times
    total_wait_time = 0.0
    completed_requests = 0
    request_times.clear()
    
    await redis_client.publish("elevator_network", json.dumps({"type": "RESET_AGENT"}))
    await manager.broadcast_to_frontend({
        "type": "METRICS_UPDATE",
        "completed": 0,
        "avg_wait": 0.00
    })
    return {"message": "System reset"}

@app.post("/break/{elevator_id}")
async def break_elevator(elevator_id: int):
    await redis_client.publish("elevator_network", json.dumps({
        "type": "STATUS_CHANGE",
        "target": elevator_id,
        "status": "BROKEN"
    }))
    return {"message": f"Elevator {elevator_id} break signal sent"}

@app.post("/fix/{elevator_id}")
async def fix_elevator(elevator_id: int):
    await redis_client.publish("elevator_network", json.dumps({
        "type": "STATUS_CHANGE",
        "target": elevator_id,
        "status": "ACTIVE"
    }))
    return {"message": f"Elevator {elevator_id} fix signal sent"}