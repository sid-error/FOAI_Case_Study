# Smart Elevator Group Controller - Decentralized P2P Multi-Agent System

## Abstract
This project simulates a 10-story building with three autonomous elevators governed by a **fully decentralized, Peer-to-Peer (P2P)** multi-agent architecture. The previous central auctioneer has been removed in favor of a distributed consensus model over a lightweight Redis Pub/Sub message broker.

### The Agents & Multi-Agent Mechanics
*   **Decentralized Elevator Agents:** Autonomous Python agents that track their own physical state (current floor, direction, operational status, queue, and physical capacity). 
*   **P2P Bidding & Consensus:** When a passenger request is dropped into the network, agents calculate their bids based on the SCAN directional heuristic. They broadcast their bids directly to each other. Agents wait for a short consensus window to collect all bids. If an agent determines it has the lowest bid, it claims the task.
*   **Resource Caps & Physical Constraints:** 
    *   **Queue Cap:** Elevators can only hold up to 10 active tasks. If exceeded, they abstain from bidding (bid 999999).
    *   **Physical Capacity:** Elevators have a physical limit of 20 people. Capacity dynamically updates only when the physical doors open at pickup and dropoff. If a new request exceeds available capacity, the agent abstains from bidding.
*   **API Gateway (No Logic):** A FastAPI service simply forwards requests from the UI into the Redis network and streams the live P2P network logs back to the frontend dashboard.
*   **Transparent Network Logs:** To prove the decentralized communication, every network event (broadcasts, bids, claims) is streamed in real-time to the dashboard console.

### Core Features
*   **Real-Time Visual Simulation:** A live HTML5 canvas interface rendering physical agent positions and system-wide metrics.
*   **Dual Operation Modes:** Manually dispatch requests from specific floors (including passenger count) or trigger the Auto Simulation for continuous, randomized system traffic.
*   **Environmental Shocks:** Live fault-injection controls that allow you to instantly "Break" or "Fix" specific agents, forcing the surviving multi-agent network to dynamically adapt and shoulder the workload.

---

## Setup and Installation

### Docker Deployment (Mandatory for P2P Cluster)
Because this is a distributed system relying on a Redis message broker and multiple independent agent containers, Docker Compose is the required method for deployment.

1. Ensure Docker Desktop is running on your machine.
2. Open Windows PowerShell and navigate to the project root directory:
   ```powershell
   cd path\to\FOAI_Case_Study
   ```
3. Build and launch the cluster using Docker Compose:
   ```powershell
   docker-compose up --build
   ```

---

## How to Run

1. **Launch the Backend Cluster:** Run `docker-compose up --build` as shown above. This will start:
   - Redis Message Broker
   - API/WebSocket Gateway
   - Agent 1, Agent 2, Agent 3

2. **Launch the Frontend Simulation:**
   Open your standard File Explorer and navigate to `FOAI_Case_Study\frontend\`. Double-click the `index.html` file to open it in any modern web browser (Chrome, Edge, Firefox). The dashboard will automatically connect to the API Gateway via WebSockets.

3. **Interact with the System:**
   - Use the **Command Center** to dispatch requests manually. You can specify Pickup, Dropoff, and the Number of People.
   - Watch the **Agent Network Log** in real-time to see the agents broadcasting bids and resolving the auction autonomously.
   - Toggle **Auto Simulation** to generate continuous traffic.
   - Click **Break E1** to simulate a critical failure and watch the other agents pick up the slack.