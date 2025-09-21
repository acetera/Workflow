"""
vast.ai deployment automation with containerized RCKangaroo.
Handles instance rental, container deployment, and worker management.
"""

import asyncio
import httpx
from typing import Dict, List, Optional
import json


class VastAIDeployer:
    """Automates vast.ai instance deployment."""

    def __init__(self, api_key: str, container_image: str):
        self.api_key = api_key
        self.container_image = container_image
        self.base_url = "https://console.vast.ai/api/v0"
        self.active_instances: Dict[str, Dict] = {}

    async def search_offers(
        self,
        gpu_model: str = "RTX_4090",
        max_price: float = 0.50,
        min_cuda: float = 11.0
    ) -> List[Dict]:
        """Search for available GPU instances."""

        search_params = {
            "q": {
                "gpu_name": {"like": gpu_model.replace("_", " ")},
                "dph_total": {"lte": max_price},
                "cuda_max_good": {"gte": min_cuda},
                "verified": {"eq": True}
            },
            "type": "on-demand"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/bundles",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=search_params
            )
            response.raise_for_status()
            return response.json()["offers"]

    async def deploy_worker(
        self,
        offer_id: str,
        worker_id: str,
        orchestrator_url: str,
        puzzle_number: int
    ) -> Dict:
        """Deploy worker container to vast.ai instance."""

        # Container run command
        container_cmd = f"""
        python3 -c "
        import os
        import time
        import subprocess
        import requests

        # Set environment
        os.environ['WORKER_ID'] = '{worker_id}'
        os.environ['ORCHESTRATOR_URL'] = '{orchestrator_url}'
        os.environ['PUZZLE_NUMBER'] = '{puzzle_number}'

        # Download or verify RCKangaroo binary
        print('Preparing RCKangaroo binary...')

        # Register with orchestrator and start work
        print(f'Starting worker {worker_id}...')
        from worker.main import main
        main()
        "
        """

        deployment_config = {
            "image": self.container_image,
            "env": {
                "WORKER_ID": worker_id,
                "ORCHESTRATOR_URL": orchestrator_url,
                "PUZZLE_NUMBER": str(puzzle_number),
                "NVIDIA_VISIBLE_DEVICES": "all"
            },
            "runtype": "ssh",
            "image_login": "",
            "python_utf8": True,
            "lang_utf8": True,
            "use_jupyter_lab": False,
            "jupyter_dir": "/app",
            "disk": 10,  # GB
            "label": f"puzzle-solver-{worker_id}"
        }

        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{self.base_url}/asks/{offer_id}/",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=deployment_config
            )
            response.raise_for_status()

            instance_info = response.json()
            self.active_instances[worker_id] = {
                "instance_id": instance_info["new_contract"],
                "offer_id": offer_id,
                "status": "deploying",
                "deployed_at": time.time()
            }

            return instance_info

    async def deploy_fleet(
        self,
        num_workers: int,
        orchestrator_url: str,
        puzzle_number: int,
        gpu_model: str = "RTX_4090"
    ) -> List[Dict]:
        """Deploy multiple workers across vast.ai."""

        # Search for offers
        offers = await self.search_offers(gpu_model=gpu_model)

        if len(offers) < num_workers:
            raise ValueError(f"Only {len(offers)} offers available, need {num_workers}")

        # Sort by price (cheapest first)
        offers.sort(key=lambda x: x["dph_total"])

        deployments = []

        for i in range(num_workers):
            worker_id = f"vast-worker-{i:03d}"
            offer = offers[i]

            print(f"Deploying {worker_id} on {offer['gpu_name']} @ ${offer['dph_total']:.3f}/hr")

            deployment = await self.deploy_worker(
                offer_id=offer["id"],
                worker_id=worker_id,
                orchestrator_url=orchestrator_url,
                puzzle_number=puzzle_number
            )

            deployments.append({
                "worker_id": worker_id,
                "gpu_model": offer["gpu_name"],
                "price_per_hour": offer["dph_total"],
                "deployment": deployment
            })

            # Small delay between deployments
            await asyncio.sleep(2)

        return deployments

    async def monitor_instances(self) -> Dict[str, str]:
        """Monitor status of active instances."""
        statuses = {}

        async with httpx.AsyncClient() as client:
            for worker_id, instance_info in self.active_instances.items():
                try:
                    response = await client.get(
                        f"{self.base_url}/instances/{instance_info['instance_id']}/",
                        headers={"Authorization": f"Bearer {self.api_key}"}
                    )

                    if response.status_code == 200:
                        instance = response.json()
                        statuses[worker_id] = instance["actual_status"]
                    else:
                        statuses[worker_id] = "unknown"

                except Exception as e:
                    statuses[worker_id] = f"error: {e}"

        return statuses

    async def terminate_instance(self, worker_id: str) -> bool:
        """Terminate a specific worker instance."""
        if worker_id not in self.active_instances:
            return False

        instance_info = self.active_instances[worker_id]

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{self.base_url}/instances/{instance_info['instance_id']}/",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )

            if response.status_code == 200:
                del self.active_instances[worker_id]
                return True

        return False

    async def terminate_all(self) -> int:
        """Terminate all active instances."""
        terminated = 0

        for worker_id in list(self.active_instances.keys()):
            if await self.terminate_instance(worker_id):
                terminated += 1

        return terminated

    def get_fleet_cost(self) -> float:
        """Calculate current hourly cost of fleet."""
        # This would need to track the actual pricing from deployments
        # For now, return estimated cost
        return len(self.active_instances) * 0.40  # Rough estimate


# Example usage functions
async def deploy_puzzle_fleet():
    """Example: Deploy a fleet for puzzle solving."""

    # Initialize deployer with your container
    deployer = VastAIDeployer(
        api_key="your-vast-api-key",
        container_image="your-registry.com/puzzle-solver-worker:latest"
    )

    # Deploy 5 workers for puzzle 135
    deployments = await deployer.deploy_fleet(
        num_workers=5,
        orchestrator_url="https://your-orchestrator.com",
        puzzle_number=135,
        gpu_model="RTX_4090"
    )

    print(f"Deployed {len(deployments)} workers")

    # Monitor for a while
    for i in range(10):
        await asyncio.sleep(30)
        statuses = await deployer.monitor_instances()
        print(f"Instance statuses: {statuses}")

    # Cleanup
    terminated = await deployer.terminate_all()
    print(f"Terminated {terminated} instances")


if __name__ == "__main__":
    # This would be called from the orchestrator
    asyncio.run(deploy_puzzle_fleet())