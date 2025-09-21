"""
Main worker process for GPU-based puzzle solving.
Connects to orchestrator and runs RCKangaroo on assigned work.
"""

import asyncio
import os
import json
import subprocess
import time
from datetime import datetime
from typing import Optional, Dict, Any

import httpx
from worker.binary_manager import get_rckang_path, verify_rckang_available


class PuzzleWorker:
    """Main worker class for GPU puzzle solving."""

    def __init__(self):
        self.worker_id = os.getenv("WORKER_ID", f"worker-{int(time.time())}")
        self.orchestrator_url = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")
        self.gpu_model = os.getenv("GPU_MODEL", "unknown")
        self.expected_speed = int(os.getenv("EXPECTED_SPEED", "8000000000"))

        self.assignment: Optional[Dict] = None
        self.rckang_process: Optional[subprocess.Popen] = None
        self.running = False

    async def register_with_orchestrator(self) -> bool:
        """Register this worker with the orchestrator."""
        registration_data = {
            "worker_id": self.worker_id,
            "gpu_model": self.gpu_model,
            "expected_speed": self.expected_speed
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.orchestrator_url}/api/workers/register",
                    json=registration_data,
                    timeout=30.0
                )
                response.raise_for_status()

                self.assignment = response.json()
                print(f"✅ Registered with orchestrator. Assignment received:")
                print(f"  Range: {self.assignment['start_key']} to {self.assignment['end_key']}")
                print(f"  DP bits: {self.assignment['dp_bits']}")
                return True

        except Exception as e:
            print(f"❌ Failed to register with orchestrator: {e}")
            return False

    async def start_rckang_process(self) -> bool:
        """Start RCKangaroo process with assigned work."""
        if not self.assignment:
            print("❌ No work assignment available")
            return False

        try:
            rckang_path = get_rckang_path()
            print(f"Using RCKangaroo at: {rckang_path}")

            # Build RCKangaroo command
            cmd = [
                rckang_path,
                "-gpu", "0",  # Use first GPU
                "-dp", str(self.assignment["dp_bits"]),
                "-range", f"{self.assignment['start_key']}:{self.assignment['end_key']}",
                "-pubkey", self.assignment["public_key_hex"],
                "-o", "/tmp/dps.txt",  # Output file for DPs
                "-v"  # Verbose
            ]

            print(f"Starting RCKangaroo: {' '.join(cmd)}")

            # Start process
            self.rckang_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            print("✅ RCKangaroo process started")
            return True

        except Exception as e:
            print(f"❌ Failed to start RCKangaroo: {e}")
            return False

    async def monitor_and_submit_dps(self):
        """Monitor RCKangaroo output and submit DPs to orchestrator."""
        last_dp_check = 0
        dp_file = "/tmp/dps.txt"

        while self.running and self.rckang_process:
            # Check if process is still running
            if self.rckang_process.poll() is not None:
                print("⚠️  RCKangaroo process exited")
                break

            # Check for new DPs in output file
            if os.path.exists(dp_file):
                try:
                    with open(dp_file, 'r') as f:
                        lines = f.readlines()[last_dp_check:]

                    for line in lines:
                        if line.strip():
                            await self._submit_dp_from_line(line.strip())

                    last_dp_check += len(lines)

                except Exception as e:
                    print(f"Error reading DP file: {e}")

            # Check RCKangaroo output for status
            try:
                # Non-blocking read from stdout
                import select
                if select.select([self.rckang_process.stdout], [], [], 0)[0]:
                    output = self.rckang_process.stdout.readline()
                    if output:
                        print(f"RCKang: {output.strip()}")

                        # Check for collision in output
                        if "COLLISION" in output.upper() or "FOUND" in output.upper():
                            print("🎉 COLLISION DETECTED!")
                            await self._handle_collision(output)

            except Exception as e:
                print(f"Error monitoring RCKangaroo: {e}")

            await asyncio.sleep(1)  # Check every second

    async def _submit_dp_from_line(self, line: str):
        """Parse DP line and submit to orchestrator."""
        try:
            # Parse RCKangaroo DP output format
            # Expected format: "DP: x=<hex> y=<hex> type=<tame|wild> dist=<int>"
            parts = line.split()
            if not parts[0] == "DP:":
                return

            dp_data = {}
            for part in parts[1:]:
                key, value = part.split('=', 1)
                dp_data[key] = value

            submission = {
                "worker_id": self.worker_id,
                "x": dp_data["x"],
                "y": dp_data["y"],
                "walk_type": dp_data["type"],
                "distance": int(dp_data["dist"]),
                "timestamp": time.time()
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.orchestrator_url}/api/dp/submit",
                    json=submission,
                    timeout=10.0
                )
                response.raise_for_status()

                result = response.json()
                if result.get("collision_found"):
                    print("🎉 COLLISION FOUND BY ORCHESTRATOR!")
                    print(f"Collision data: {result['collision_data']}")

        except Exception as e:
            print(f"Error submitting DP: {e}")

    async def _handle_collision(self, output: str):
        """Handle collision found by RCKangaroo."""
        print("🚨 COLLISION HANDLING")
        print(f"RCKangaroo output: {output}")

        # Stop the current process
        if self.rckang_process:
            self.rckang_process.terminate()

        # In a real scenario, would extract private key and submit to orchestrator
        # For now, just log the achievement
        print("✅ Work completed - collision found!")

    async def run(self):
        """Main worker loop."""
        print(f"🚀 Starting Puzzle Worker {self.worker_id}")
        print(f"   GPU Model: {self.gpu_model}")
        print(f"   Expected Speed: {self.expected_speed:,} keys/sec")
        print(f"   Orchestrator: {self.orchestrator_url}")

        # Verify RCKangaroo is available
        if not verify_rckang_available():
            print("❌ RCKangaroo not available")
            return False

        # Register with orchestrator
        if not await self.register_with_orchestrator():
            return False

        # Start RCKangaroo
        if not await self.start_rckang_process():
            return False

        # Main work loop
        self.running = True
        try:
            await self.monitor_and_submit_dps()
        except KeyboardInterrupt:
            print("⏹️  Worker stopped by user")
        except Exception as e:
            print(f"❌ Worker error: {e}")
        finally:
            await self.cleanup()

        return True

    async def cleanup(self):
        """Clean up worker resources."""
        self.running = False

        if self.rckang_process:
            print("Terminating RCKangaroo process...")
            self.rckang_process.terminate()
            try:
                self.rckang_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.rckang_process.kill()

        print("✅ Worker cleanup complete")


async def main():
    """Main entry point."""
    worker = PuzzleWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
