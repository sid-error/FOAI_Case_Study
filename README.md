# Smart Elevator Group Controller - Multi-Agent System

## Team Members
Kalyani H Karuvelil - CB.SC.U4CSE23423
Madhavan G Menon    - CB.SC.U4CSE23428
Sidharth S Nair     - CB.SC.U4CSE23443
Soundarya Satalgoan     - CB.SC.U4CSE23447

---

## Abstract
This project simulates a 10-story building with three autonomous elevators governed by a decentralized, multi-agent architecture. Instead of relying on a monolithic central routing algorithm to coordinate movement, the system utilizes the **Contract Net Protocol (CNP)** and a localized **SCAN directional heuristic** to minimize passenger wait times through real-time bidding and spatial task delegation.

### The Agents & Multi-Agent Mechanics
*   **Central Managing Agent (Auctioneer):** A FastAPI backend that listens for incoming passenger requests, broadcasts "Call for Proposals" to the active elevator network, and resolves auctions by assigning tasks to the lowest bidder.
*   **Elevator Agents (Bidders):** Autonomous Python agents that track their own physical state (current floor, direction, operational status, and capacity). 
*   **Bid Calculation:** When a request is broadcast, elevators calculate a "cost" to take the job. An elevator already heading in the direction of the passenger and passing their floor bids very low. An elevator moving away bids exceptionally high.
*   **Simulation Metric:** The primary performance metric is the rolling average passenger wait time, calculated from the moment a request is initiated to the moment the elevator doors open at the destination.

### Core Features
*   **Real-Time Visual Simulation:** A live HTML5 canvas interface rendering physical agent positions and system-wide metrics.
*   **Dual Operation Modes:** Manually dispatch requests from specific floors or trigger the Auto Simulation for continuous, randomized system traffic.
*   **Environmental Shocks:** Live fault-injection controls that allow you to instantly "Break" or "Fix" specific agents, forcing the surviving multi-agent network to dynamically adapt and shoulder the workload.

---

## Prerequisites
Before you begin, ensure you have the following installed on your system:
*   **Python 3.10 or higher**
*   **Docker Desktop** (Required only for Docker deployment)
*   **Git** (Optional, for cloning the repository)

---

## Setup and Installation

### Option 1: Docker Deployment (Recommended)
This approach guarantees an isolated environment and orchestrates the backend cluster automatically.

1. Ensure Docker Desktop is running on your machine.
2. Open Windows PowerShell and navigate to the project root directory:
   ```powershell
   cd path\to\FOAI_Case_Study
3. Build and launch the cluster using Docker Compose:
   docker-compose up --build

### Option 2: Local Deployment

1. Open Windows PowerShell and navigate to the project root directory:
   ```powershell
   cd path\to\FOAI_Case_Study
2. Create and activate a Python virtual environment:
   python -m venv venv
   venv\Scripts\activate
3. Install the required Python dependencies:
   pip install -r requirements.txt

---

## How to Run
If you used Option 1 (Docker), the backend cluster is already running. Skip to Step 3. If you used Option 2 (Local Deployment), you must manually start the network components:

1. Start the Central Manager
In your active PowerShell terminal, start the FastAPI server:
uvicorn backend.main:app --host 127.0.0.1 --port 8000

2. Start the Elevator Agents
Open three new separate PowerShell tabs. In each tab, navigate to the project directory, activate the virtual environment, and start an agent with a unique ID (1, 2, and 3):
Tab 1:
cd path\to\FOAI_Case_Study
venv\Scripts\activate
python agents\elevator_agent.py 1
Tab2:
cd path\to\FOAI_Case_Study
venv\Scripts\activate
python agents\elevator_agent.py 2
Tab3:
cd path\to\FOAI_Case_Study
venv\Scripts\activate
python agents\elevator_agent.py 3

3. Launch the Frontend Simulation
Open your standard File Explorer and navigate to FOAI_Case_Study\frontend\. Double-click the index.html file to open it in any modern web browser (Chrome, Edge, Firefox). The dashboard will automatically connect to the backend via WebSockets. You can now use the Command Center on the left to toggle between Manual and Auto Simulation modes, trigger system resets, or inject environmental shocks.

---
