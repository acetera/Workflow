"""
Main orchestrator service for the Bitcoin puzzle solver.
Coordinates workers, manages DP database, and detects collisions.
"""

from typing import Dict, List, Optional
import asyncio
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from orchestrator.work_distributor import WorkDistributor, WorkAssignment, PUZZLE_CONFIGS
from shared.distinguished_point import DistinguishedPoint, CollisionResult
from shared.memory_dp_database import MemoryDPDatabase


class WorkerRegistration(BaseModel):
    """Worker registration request."""
    worker_id: str
    gpu_model: str
    expected_speed: int  # Keys per second


class DPSubmission(BaseModel):
    """Distinguished point submission from worker."""
    worker_id: str
    x: str  # Hex string
    y: str  # Hex string
    walk_type: str  # "tame" or "wild"
    distance: int
    timestamp: float


class OrchestratorService:
    """Main orchestrator service."""

    def __init__(self):
        self.work_distributor = WorkDistributor()
        self.dp_database = MemoryDPDatabase()
        self.registered_workers: Dict[str, Dict] = {}
        self.active_puzzle: Optional[int] = None
        self.collision_callbacks: List = []

        # Performance tracking
        self.start_time: Optional[float] = None
        self.total_dps_received = 0
        self.total_keys_searched = 0

    async def register_worker(self, registration: WorkerRegistration) -> WorkAssignment:
        """Register a new worker and assign work."""
        if not self.active_puzzle:
            raise HTTPException(status_code=400, detail="No active puzzle")

        worker_info = {
            "gpu_model": registration.gpu_model,
            "expected_speed": registration.expected_speed,
            "registered_at": datetime.now().timestamp(),
            "last_seen": datetime.now().timestamp(),
            "status": "active"
        }

        self.registered_workers[registration.worker_id] = worker_info

        # Get existing assignment or create new one
        try:
            assignment = self.work_distributor.get_assignment(registration.worker_id)
        except ValueError:
            # Create new assignment for this worker
            puzzle_config = PUZZLE_CONFIGS[self.active_puzzle]
            assignments = self.work_distributor.distribute_work(
                puzzle_number=self.active_puzzle,
                public_key_hex=puzzle_config["public_key"],
                num_workers=1  # Single assignment
            )
            assignment = assignments[0]
            assignment.worker_id = registration.worker_id

        return assignment

    async def submit_distinguished_point(self, submission: DPSubmission) -> Dict:
        """Process DP submission from worker."""
        # Validate worker is registered
        if submission.worker_id not in self.registered_workers:
            raise HTTPException(status_code=400, detail="Worker not registered")

        # Update last seen
        self.registered_workers[submission.worker_id]["last_seen"] = datetime.now().timestamp()

        # Create DP object
        try:
            dp = DistinguishedPoint(
                x=int(submission.x, 16),
                y=int(submission.y, 16),
                walk_type=submission.walk_type,
                distance=submission.distance,
                worker_id=submission.worker_id,
                timestamp=submission.timestamp
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid DP: {e}")

        # Store DP and check for collision
        collision = self.dp_database.store_dp(dp)
        self.total_dps_received += 1

        response = {
            "status": "accepted",
            "dp_count": self.total_dps_received,
            "collision_found": False
        }

        if collision:
            response["collision_found"] = True
            response["collision_data"] = {
                "tame_worker": collision.tame_dp.worker_id,
                "wild_worker": collision.wild_dp.worker_id,
                "point_x": hex(collision.tame_dp.x),
                "point_y": hex(collision.tame_dp.y)
            }

            # Notify collision callbacks
            for callback in self.collision_callbacks:
                await callback(collision)

        return response

    async def start_puzzle(self, puzzle_number: int, num_workers: int = 1) -> Dict:
        """Start solving a specific puzzle."""
        if puzzle_number not in PUZZLE_CONFIGS:
            raise HTTPException(status_code=400, detail=f"Puzzle {puzzle_number} not configured")

        self.active_puzzle = puzzle_number
        self.start_time = datetime.now().timestamp()

        # Clear previous state
        self.dp_database.clear_all()
        self.registered_workers.clear()
        self.total_dps_received = 0
        self.total_keys_searched = 0

        puzzle_config = PUZZLE_CONFIGS[puzzle_number]

        return {
            "puzzle_number": puzzle_number,
            "public_key": puzzle_config["public_key"],
            "status": puzzle_config["status"],
            "workers_needed": num_workers,
            "started_at": self.start_time
        }

    def get_system_stats(self) -> Dict:
        """Get comprehensive system statistics."""
        dp_stats = self.dp_database.get_stats()
        work_stats = self.work_distributor.get_assignment_stats()

        # Calculate runtime
        runtime_seconds = 0
        if self.start_time:
            runtime_seconds = datetime.now().timestamp() - self.start_time

        # Calculate total speed across all workers
        total_expected_speed = sum(
            worker["expected_speed"] for worker in self.registered_workers.values()
        )

        # Estimate keys searched based on runtime and speed
        estimated_keys_searched = int(total_expected_speed * runtime_seconds)

        return {
            "puzzle": {
                "active_puzzle": self.active_puzzle,
                "runtime_seconds": runtime_seconds,
                "runtime_hours": runtime_seconds / 3600
            },
            "workers": {
                "registered": len(self.registered_workers),
                "active": len([w for w in self.registered_workers.values()
                             if w["status"] == "active"]),
                "total_expected_speed": total_expected_speed,
                "workers": dict(self.registered_workers)
            },
            "distinguished_points": dp_stats,
            "work_distribution": work_stats,
            "performance": {
                "total_dps_received": self.total_dps_received,
                "estimated_keys_searched": estimated_keys_searched,
                "dp_rate_per_second": self.total_dps_received / max(runtime_seconds, 1)
            }
        }


# FastAPI application
app = FastAPI(title="Bitcoin Puzzle Solver Orchestrator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global orchestrator instance
orchestrator = OrchestratorService()


@app.post("/api/workers/register")
async def register_worker(registration: WorkerRegistration):
    """Register a new worker."""
    assignment = await orchestrator.register_worker(registration)
    return assignment.to_dict()


@app.post("/api/dp/submit")
async def submit_dp(submission: DPSubmission):
    """Submit a distinguished point."""
    return await orchestrator.submit_distinguished_point(submission)


@app.post("/api/puzzle/start/{puzzle_number}")
async def start_puzzle(puzzle_number: int, num_workers: int = 1):
    """Start solving a puzzle."""
    return await orchestrator.start_puzzle(puzzle_number, num_workers)


@app.get("/api/stats")
async def get_stats():
    """Get system statistics."""
    return orchestrator.get_system_stats()


@app.get("/api/puzzle/configs")
async def get_puzzle_configs():
    """Get available puzzle configurations."""
    return PUZZLE_CONFIGS


@app.websocket("/ws/stats")
async def websocket_stats(websocket: WebSocket):
    """WebSocket endpoint for real-time statistics."""
    await websocket.accept()
    try:
        while True:
            stats = orchestrator.get_system_stats()
            await websocket.send_text(json.dumps(stats))
            await asyncio.sleep(1)  # Send stats every second
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Bitcoin Puzzle Solver Orchestrator",
        "status": "running",
        "active_puzzle": orchestrator.active_puzzle,
        "registered_workers": len(orchestrator.registered_workers)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)