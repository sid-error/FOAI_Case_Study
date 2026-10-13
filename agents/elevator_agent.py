import asyncio
import json
import random
import sys
import os
import time
from datetime import datetime
import redis.asyncio as redis

class ElevatorAgent:
    """
    Decentralized Elevator Agent using Redis Pub/Sub for P2P communication.
    Operates without a central auctioneer by communicating directly with peers.
    """
    def __init__(self, elevator_id):
        self.elevator_id = int(elevator_id)
        self.agent_name = f"E{self.elevator_id}"
        self.current_floor = random.randint(1, 10)
        self.direction = "IDLE"
        self.status = "ACTIVE"
        
        # Resource limits defined by physical constraints
        self.active_requests = {} # Current queue of tasks
        self.current_occupancy = 0 # Current number of people in the physical car
        self.MAX_REQUESTS = 10 # Request Queue Cap (Task Limit)
        self.MAX_CAPACITY = 20 # Physical Passenger Capacity Sensor limit
        
        self.auctions = {} # Track active P2P bidding processes
        
        # Connect to the Redis message broker that acts as the communication fabric
        redis_host = os.getenv("REDIS_HOST", "127.0.0.1")
        self.redis = redis.Redis(host=redis_host, port=6379, decode_responses=True)

    async def log_event(self, receiver, msg_type, payload):
        """
        Format and broadcast logs strictly adhering to the transparent logging requirement.
        Format: [TIMESTAMP] [SENDER_ID] -> [RECEIVER_ID_OR_BROADCAST] | MSG_TYPE: Payload
        """
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        log_str = f"[{timestamp}] [{self.agent_name}] -> [{receiver}] | {msg_type}: {payload}"
        
        # Print to Docker terminal for academic defense visibility
        print(log_str, flush=True)
        
        # Broadcast to the Live Network Log UI in the frontend
        await self.redis.publish("elevator_logs", json.dumps({"message": log_str}))

    def calculate_bid(self, pickup_floor, dropoff_floor):
        """
        Calculate movement cost using the SCAN directional heuristic.
        The goal is to minimize distance and prefer tasks in the current direction of travel.
        """
        # If the elevator is broken, it issues an extreme penalty bid so it won't win the task
        if self.status == "BROKEN":
            return 999999
            
        req_dir = "UP" if dropoff_floor > pickup_floor else "DOWN"
        distance = abs(self.current_floor - pickup_floor)
        
        # If idle, the cost is simply the distance to the pickup floor
        if self.direction == "IDLE":
            return distance
            
        # If moving UP, favor requests that are also going UP and are ahead of us
        if self.direction == "UP":
            if pickup_floor >= self.current_floor and req_dir == "UP":
                return distance 
            else:
                # Add a substantial penalty if the request is behind us or going DOWN
                return distance + 20 
                
        # If moving DOWN, favor requests that are also going DOWN and are below us
        if self.direction == "DOWN":
            if pickup_floor <= self.current_floor and req_dir == "DOWN":
                return distance
            else:
                # Add penalty for inefficient change of direction
                return distance + 20

    async def broadcast_state(self):
        """Broadcast physical state for UI updates."""
        await self.redis.publish("elevator_network", json.dumps({
            "type": "STATE_UPDATE",
            "elevator_id": self.elevator_id,
            "floor": self.current_floor,
            "status": self.status
        }))

    async def run_auction_timer(self, req_id):
        """
        Distributed Consensus Mechanism (Simplistic Timeout-based Agreement)
        Instead of a master node deciding, agents wait for a fixed 1.0 second 
        window to collect bids from all peers in the P2P network.
        """
        # Wait for the network to settle and collect bids
        await asyncio.sleep(1.0)
        
        if req_id not in self.auctions:
            return # Auction was cancelled or someone else claimed it early
            
        auction = self.auctions[req_id]
        my_bid = auction["my_bid"]
        bids = auction["bids"] # List of (cost, agent_id)
        
        # The consensus rule: lowest bid cost wins. 
        # In case of a tie, the lowest agent_id takes priority to prevent deadlocks.
        winner = min(bids, key=lambda x: (x[0], x[1]))
        
        # If I am the winner according to the decentralized consensus rule
        if winner[1] == self.elevator_id:
            if my_bid < 999999: # Only claim the task if we haven't penalized ourselves out of it
                # Log the claim for transparency
                await self.log_event("BROADCAST", "TASK_CLAIM", f'{{"request_id": "{req_id}"}}')
                
                # Broadcast the claim to peers so they drop the task
                await self.redis.publish("elevator_network", json.dumps({
                    "type": "TASK_CLAIM",
                    "request_id": req_id,
                    "elevator_id": self.elevator_id
                }))
                
                # Assign the task to our own active queue
                self.active_requests[req_id] = {
                    "pickup": auction["pickup"],
                    "dropoff": auction["dropoff"],
                    "people": auction["people"],
                    "state": "WAITING"
                }
        
        # Auction is resolved, clean up state
        del self.auctions[req_id]

    async def handle_message(self, data):
        """Process incoming P2P network messages directly from the Redis broker."""
        msg_type = data.get("type")
        
        if msg_type == "BID_REQUEST":
            req_id = data["request_id"]
            pickup = data["pickup"]
            dropoff = data["dropoff"]
            people = data.get("people", 1)
            
            # 1. Request Queue Cap Check
            # Abstain instantly if we have 10 or more active tasks
            if len(self.active_requests) >= self.MAX_REQUESTS:
                cost = 999999
                
            # 2. Physical Capacity Sensor Check (Pre-calculation)
            # Abstain if adding these people would exceed our maximum limit of 20
            elif self.current_occupancy + people > self.MAX_CAPACITY:
                cost = 999999
                
            # 3. Normal Bid Calculation
            else:
                cost = self.calculate_bid(pickup, dropoff)
                
            # Track this auction locally to collect incoming bids from peers
            self.auctions[req_id] = {
                "my_bid": cost,
                "pickup": pickup,
                "dropoff": dropoff,
                "people": people,
                "bids": [(cost, self.elevator_id)]
            }
            
            # Announce our bid transparently to the network
            payload = f'{{"cost": {cost}, "request_id": "{req_id}"}}'
            await self.log_event("BROADCAST", "BID", payload)
            
            # Publish the actual bid to peers for their local consensus calculation
            await self.redis.publish("elevator_network", json.dumps({
                "type": "BID",
                "request_id": req_id,
                "elevator_id": self.elevator_id,
                "cost": cost
            }))
            
            # Start the timeout window to resolve this auction
            asyncio.create_task(self.run_auction_timer(req_id))
            
        elif msg_type == "BID":
            req_id = data["request_id"]
            if req_id in self.auctions:
                # Add the peer's bid to our local auction state for consensus calculation
                self.auctions[req_id]["bids"].append((data["cost"], data["elevator_id"]))
                
        elif msg_type == "TASK_CLAIM":
            req_id = data["request_id"]
            if req_id in self.auctions:
                if data["elevator_id"] != self.elevator_id:
                    # A peer claimed the task (won the auction). Remove it from our local state.
                    del self.auctions[req_id]
                    
        elif msg_type == "RESET_AGENT":
            self.status = "RESETTING"
            await asyncio.sleep(0.5) 
            self.active_requests.clear()
            self.auctions.clear()
            self.direction = "IDLE"
            self.current_floor = random.randint(1, 10)
            self.current_occupancy = 0
            self.status = "ACTIVE"
            await self.broadcast_state()
            
        elif msg_type == "STATUS_CHANGE":
            if data.get("target") == self.elevator_id:
                self.status = data.get("status")
                if self.status == "BROKEN":
                    self.active_requests.clear()
                    self.auctions.clear()
                    self.direction = "IDLE"
                    self.current_occupancy = 0
                await self.broadcast_state()

    async def movement_loop(self):
        """Continuous background task managing the elevator's physical movement."""
        while True:
            if self.status in ["RESETTING", "BROKEN"]:
                await asyncio.sleep(0.5)
                continue
                
            if not self.active_requests:
                if self.direction != "IDLE":
                    self.direction = "IDLE"
                    await self.broadcast_state()
                await asyncio.sleep(0.5)
                continue
                
            # Collect all current target floors (pickups and dropoffs)
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
                
            # If we reached a target floor, process doors opening
            if self.current_floor in targets:
                await asyncio.sleep(0.5) # Simulating doors opening delay
                
                # Dropoff logic (Passengers leave)
                completed_ids = []
                for req_id, req in self.active_requests.items():
                    if req["state"] == "ONBOARD" and req["dropoff"] == self.current_floor:
                        completed_ids.append(req_id)
                        # Physical Capacity Update: decrease occupancy when doors open at dropoff
                        self.current_occupancy -= req["people"]
                
                for req_id in completed_ids:
                    del self.active_requests[req_id]
                    # Notify the gateway that the task is completed for metrics calculation
                    await self.redis.publish("elevator_network", json.dumps({
                        "type": "TASK_COMPLETED",
                        "request_id": req_id,
                        "elevator_id": self.elevator_id
                    }))
                    
                # Pickup logic (Passengers board)
                for req_id, req in self.active_requests.items():
                    if req["state"] == "WAITING" and req["pickup"] == self.current_floor:
                        req_dir = "UP" if req["dropoff"] > req["pickup"] else "DOWN"
                        targets_ahead = [t for t in targets if (t > self.current_floor if self.direction == "UP" else t < self.current_floor)]
                        
                        # Only pick them up if they are going in our current direction, 
                        # or if there's no one ahead so we will reverse soon anyway.
                        if req_dir == self.direction or not targets_ahead:
                            req["state"] = "ONBOARD"
                            # Physical Capacity Update: increase occupancy when doors open at pickup
                            self.current_occupancy += req["people"]

            # Refresh targets because state may have changed (passengers boarded)
            targets = set()
            for req in self.active_requests.values():
                if req["state"] == "WAITING":
                    targets.add(req["pickup"])
                elif req["state"] == "ONBOARD":
                    targets.add(req["dropoff"])

            # Determine if we should keep moving in the same direction or reverse
            targets_ahead = []
            for t in targets:
                if self.direction == "UP" and t > self.current_floor: targets_ahead.append(t)
                if self.direction == "DOWN" and t < self.current_floor: targets_ahead.append(t)
            
            if not targets_ahead and self.active_requests:
                self.direction = "DOWN" if self.direction == "UP" else "UP"
            elif not self.active_requests:
                self.direction = "IDLE"
            
            # Physically move between floors
            if self.direction != "IDLE":
                await asyncio.sleep(1) 
                if self.direction == "UP":
                    self.current_floor += 1
                elif self.direction == "DOWN":
                    self.current_floor -= 1
                
                # Broadcast the updated physical state
                await self.broadcast_state()

    async def run(self):
        """Establish connection to the P2P Redis network and process incoming messages."""
        await self.broadcast_state()
        asyncio.create_task(self.movement_loop())
        
        pubsub = self.redis.pubsub()
        await pubsub.subscribe("elevator_network")
        
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await self.handle_message(data)
        except Exception as e:
            print(f"Error in agent {self.elevator_id}: {e}")

async def main():
    """Entry point for the autonomous elevator agent."""
    agent_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    agent = ElevatorAgent(agent_id)
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())