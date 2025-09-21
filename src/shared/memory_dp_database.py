"""
In-memory distinguished point database for development and testing.
Production will use Redis, but this allows development without Redis server.
"""

from typing import Optional, Dict, Any
import json
from .distinguished_point import DistinguishedPoint, CollisionResult


class MemoryDPDatabase:
    """In-memory distinguished point database for development."""

    def __init__(self):
        """Initialize in-memory storage."""
        self.storage: Dict[str, str] = {}
        self.stats = {
            "total_dps": 0,
            "dps_tame": 0,
            "dps_wild": 0
        }

    def store_dp(self, dp: DistinguishedPoint) -> Optional[CollisionResult]:
        """
        Store distinguished point and check for collisions.

        Returns:
            CollisionResult if collision found, None otherwise
        """
        key = dp.key

        # Check if DP already exists
        if key in self.storage:
            existing_data = json.loads(self.storage[key])
            existing_dp = DistinguishedPoint.from_dict(existing_data)

            # Check for collision (different walk types at same point)
            if existing_dp.walk_type != dp.walk_type:
                return CollisionResult(existing_dp, dp)
            else:
                # Same walk type - not a collision, but log it
                print(f"Duplicate DP from same walk type: {key}")
                return None

        # Store new DP
        self.storage[key] = json.dumps(dp.to_dict())

        # Update statistics
        self.stats["total_dps"] += 1
        self.stats[f"dps_{dp.walk_type}"] += 1

        return None

    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        return {
            **self.stats,
            "memory_usage_mb": len(self.storage) * 0.001  # Rough estimate
        }

    def clear_all(self):
        """Clear all data."""
        self.storage.clear()
        self.stats = {
            "total_dps": 0,
            "dps_tame": 0,
            "dps_wild": 0
        }


def test_memory_dp_system():
    """Test the in-memory DP system."""
    from .secp256k1 import Point
    from datetime import datetime

    # Test point with trailing zeros
    test_point = Point(0x1000000000000000000000000000000000000000000000000000000000000000,
                      0x4218F20AE6C646B363DB68605822FB14264CA8D2587FDD6FBC750D587E76A7EE)

    db = MemoryDPDatabase()

    # Create test DPs
    dp1 = DistinguishedPoint(
        x=test_point.x,
        y=test_point.y,
        walk_type="tame",
        distance=12345,
        worker_id="test_worker_1",
        timestamp=datetime.now().timestamp()
    )

    # Store first DP
    collision = db.store_dp(dp1)
    assert collision is None, "No collision expected for first DP"

    # Create second DP at same point but different walk type
    dp2 = DistinguishedPoint(
        x=test_point.x,
        y=test_point.y,
        walk_type="wild",
        distance=54321,
        worker_id="test_worker_2",
        timestamp=datetime.now().timestamp()
    )

    # Store second DP - should detect collision
    collision = db.store_dp(dp2)
    assert collision is not None, "Collision should be detected"
    assert collision.tame_dp.walk_type == "tame"
    assert collision.wild_dp.walk_type == "wild"

    stats = db.get_stats()
    assert stats["total_dps"] == 2
    assert stats["dps_tame"] == 1
    assert stats["dps_wild"] == 1

    print("✅ Memory DP database tests passed")


if __name__ == "__main__":
    test_memory_dp_system()