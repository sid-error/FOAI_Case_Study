import asyncio
import websockets
import json
import random
import sys
import os

class ElevatorAgent:
    """
    Represents an autonomous elevator agent that communicates with the central manager.
    It manages its own state, bids on requests, and processes assigned tasks.
    """
    def __init__(self, elevator_id):
        self.elevator_id = elevator_id
        self.current_floor = random.randint(1, 10)
        self.direction = "IDLE"
        self.status = "ACTIVE"
        
        self.active_requests = {}
        self.pending_bids_data = {} 

    def calculate_bid(self, pickup_floor, dropoff_floor):
        """Calculate bid cost based on spatial distance and direction to optimize movement."""
        # Reject bids if the elevator is broken
        if self.status == "BROKEN":
            return 999999
            
        req_dir = "UP" if dropoff_floor > pickup_floor else "DOWN"
        distance = abs(self.current_floor - pickup_floor)
        
        if self.direction == "IDLE":
            return distance
            
        if self.direction == "UP":
            if pickup_floor >= self.current_floor and req_dir == "UP":
                return distance 
            else:
                return distance + 20 
                
        if self.direction == "DOWN":
            if pickup_floor <= self.current_floor and req_dir == "DOWN":
                return distance
            else:
                return distance + 20

    async def broadcast_state(self, websocket):
        """Send the current physical state of the elevator to the central manager."""
        await websocket.send(json.dumps({
            "type": "STATE_UPDATE",
            "elevator_id": self.elevator_id,
            "floor": self.current_floor,
            "status": self.status
        }))

    async def movement_loop(self, websocket):
        """Continuous background task managing the elevator's step-by-step movement."""
        while True:
            if self.status in ["RESETTING", "BROKEN"]:
                await asyncio.sleep(0.5)
                continue
                
            if not self.active_requests:
                if self.direction != "IDLE":
                    self.direction = "IDLE"
                    await self.broadcast_state(websocket)
                await asyncio.sleep(0.5)
                continue
                
            targets = set()
            for req in self.active_requests.values():
                if req["state"] == "WAITING":
                    targets.add(req["pickup"])
                elif req["state"] == "ONBOARD":
                    targets.add(req["dropoff"])
                    
            if not targets:
                await asyncio.sleep(0.5)
                continue
                
            if self.direction == "IDLE":
                nearest = min(targets, key=lambda f: abs(self.current_floor - f))
                self.direction = "UP" if nearest > self.current_floor else "DOWN"
                
            if self.current_floor in targets:
                await asyncio.sleep(0.5) 
                
                completed_ids = []
                for req_id, req in self.active_requests.items():
                    if req["state"] == "ONBOARD" and req["dropoff"] == self.current_floor:
                        completed_ids.append(req_id)
                
                for req_id in completed_ids:
                    del self.active_requests[req_id]
                    await websocket.send(json.dumps({
                        "type": "TASK_COMPLETED",
                        "request_id": req_id,
                        "elevator_id": self.elevator_id
                    }))
                    
                for req_id, req in self.active_requests.items():
                    if req["state"] == "WAITING" and req["pickup"] == self.current_floor:
                        req_dir = "UP" if req["dropoff"] > req["pickup"] else "DOWN"
                        targets_ahead = [t for t in targets if (t > self.current_floor if self.direction == "UP" else t < self.current_floor)]
                        
                        if req_dir == self.direction or not targets_ahead:
                            req["state"] = "ONBOARD"

            targets_ahead = []
            for t in targets:
                if self.direction == "UP" and t > self.current_floor: targets_ahead.append(t)
                if self.direction == "DOWN" and t < self.current_floor: targets_ahead.append(t)
            
            if not targets_ahead and self.active_requests:
                self.direction = "DOWN" if self.direction == "UP" else "UP"
            elif not self.active_requests:
                self.direction = "IDLE"
            
            if self.direction != "IDLE":
                await asyncio.sleep(1) 
                if self.direction == "UP":
                    self.current_floor += 1
                elif self.direction == "DOWN":
                    self.current_floor -= 1
                
                await self.broadcast_state(websocket)

    async def run(self):
        """Establish WebSocket connection and handle incoming messages from the central manager."""
        backend_host = os.getenv("BACKEND_HOST", "127.0.0.1")
        uri = f"ws://{backend_host}:8000/ws/elevator/{self.elevator_id}"
        async with websockets.connect(uri) as websocket:
            await self.broadcast_state(websocket)
            
            asyncio.create_task(self.movement_loop(websocket))
            
            try:
                while True:
                    message = await websocket.recv()
                    data = json.loads(message)

                    if data.get("type") == "BID_REQUEST":
                        req_id = data["request_id"]
                        self.pending_bids_data[req_id] = {"pickup": data["pickup"], "dropoff": data["dropoff"]}
                        
                        cost = self.calculate_bid(data["pickup"], data["dropoff"])
                        await websocket.send(json.dumps({
                            "type": "BID",
                            "elevator_id": self.elevator_id,
                            "request_id": req_id,
                            "bid_cost": cost
                        }))
                        
                    elif data.get("type") == "TASK_ASSIGNED":
                        req_id = data["request_id"]
                        if req_id in self.pending_bids_data:
                            task = self.pending_bids_data.pop(req_id)
                            self.active_requests[req_id] = {
                                "pickup": task["pickup"],
                                "dropoff": task["dropoff"],
                                "state": "WAITING"
                            }

                    elif data.get("type") == "RESET_AGENT":
                        self.status = "RESETTING"
                        await asyncio.sleep(0.5) 
                        self.active_requests.clear()
                        self.pending_bids_data.clear()
                        self.direction = "IDLE"
                        self.current_floor = random.randint(1, 10)
                        self.status = "ACTIVE"
                        await self.broadcast_state(websocket)
                        
                    elif data.get("type") == "STATUS_CHANGE":
                        if data.get("target") == self.elevator_id:
                            self.status = data.get("status")
                            if self.status == "BROKEN":
                                self.active_requests.clear()
                                self.pending_bids_data.clear()
                                self.direction = "IDLE"
                            await self.broadcast_state(websocket)

            except websockets.exceptions.ConnectionClosed:
                print("Disconnected from central manager.")

async def main():
    """Entry point for the elevator agent script."""
    agent_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    agent = ElevatorAgent(agent_id)
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())