"""
Distinguished Point (DP) handling and collision detection.
Real cryptographic operations only - no simulations.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import redis
from .secp256k1 import Point


@dataclass
class DistinguishedPoint:
    """A distinguished point found during kangaroo walk."""
    x: int  # Point x-coordinate
    y: int  # Point y-coordinate
    walk_type: str  # "tame" or "wild"
    distance: int  # Exact distance from starting point
    worker_id: str  # Worker that found this DP
    timestamp: float  # Unix timestamp

    def __post_init__(self):
        """Validate DP is actually on curve."""
        point = Point(self.x, self.y)
        if not point.is_on_curve():
            raise ValueError(f"DP at ({hex(self.x)}, {hex(self.y)}) not on secp256k1 curve")

        if self.walk_type not in ("tame", "wild"):
            raise ValueError(f"Invalid walk type: {self.walk_type}")

    @property
    def key(self) -> str:
        """Redis key for this DP."""
        return f"dp:{self.x:064x}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Redis storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DistinguishedPoint':
        """Create DP from dictionary."""
        return cls(**data)


def is_distinguished(point: Point, dp_bits: int) -> bool:
    """
    Check if point is distinguished (has required trailing zeros).

    Args:
        point: Point to check
        dp_bits: Number of trailing zero bits required

    Returns:
        True if point.x has dp_bits trailing zeros
    """
    if dp_bits <= 0:
        return False

    # Check if x-coordinate has dp_bits trailing zeros
    mask = (1 << dp_bits) - 1
    return (point.x & mask) == 0


class DPDatabase:
    """Redis-based distinguished point database with collision detection."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        """Initialize database connection."""
        self.redis = redis.from_url(redis_url, decode_responses=True)

        # Test connection
        try:
            self.redis.ping()
        except redis.ConnectionError:
            raise ConnectionError(f"Cannot connect to Redis at {redis_url}")

    def store_dp(self, dp: DistinguishedPoint) -> Optional['CollisionResult']:
        """
        Store distinguished point and check for collisions.

        Returns:
            CollisionResult if collision found, None otherwise
        """
        key = dp.key

        # Check if DP already exists
        existing_data = self.redis.get(key)

        if existing_data:
            existing_dp = DistinguishedPoint.from_dict(json.loads(existing_data))

            # Check for collision (different walk types at same point)
            if existing_dp.walk_type != dp.walk_type:
                return CollisionResult(existing_dp, dp)
            else:
                # Same walk type - not a collision, but log it
                print(f"Duplicate DP from same walk type: {key}")
                return None

        # Store new DP
        self.redis.set(key, json.dumps(dp.to_dict()))

        # Update statistics
        self.redis.incr("stats:total_dps")
        self.redis.incr(f"stats:dps_{dp.walk_type}")

        return None

    def get_stats(self) -> Dict[str, int]:
        """Get database statistics."""
        total = self.redis.get("stats:total_dps") or "0"
        tame = self.redis.get("stats:dps_tame") or "0"
        wild = self.redis.get("stats:dps_wild") or "0"

        return {
            "total_dps": int(total),
            "tame_dps": int(tame),
            "wild_dps": int(wild),
            "memory_usage_mb": self.get_memory_usage()
        }

    def get_memory_usage(self) -> float:
        """Get Redis memory usage in MB."""
        info = self.redis.info("memory")
        return info.get("used_memory", 0) / (1024 * 1024)

    def clear_all(self):
        """Clear all data (for testing only)."""
        self.redis.flushdb()


@dataclass
class CollisionResult:
    """Result of a collision between tame and wild walks."""
    tame_dp: DistinguishedPoint
    wild_dp: DistinguishedPoint

    def __post_init__(self):
        """Validate collision."""
        if self.tame_dp.x != self.wild_dp.x or self.tame_dp.y != self.wild_dp.y:
            raise ValueError("Collision DPs must be at same point")

        if self.tame_dp.walk_type == self.wild_dp.walk_type:
            raise ValueError("Collision requires different walk types")

    def solve_ecdlp(self, tame_start: int, wild_start_point: Point) -> int:
        """
        Solve ECDLP from collision.

        Args:
            tame_start: Starting private key for tame walk
            wild_start_point: Starting point for wild walk

        Returns:
            Private key corresponding to wild_start_point
        """
        # Get the tame and wild DPs
        if self.tame_dp.walk_type == "tame":
            tame = self.tame_dp
            wild = self.wild_dp
        else:
            tame = self.wild_dp
            wild = self.tame_dp

        # Import N here to avoid circular imports
        from .secp256k1 import N, public_key_from_private

        # Private key = tame_start + tame_distance - wild_distance
        # This works because:
        # tame_point = (tame_start + tame_distance) * G
        # wild_point = wild_distance * wild_start_point
        # Since they collided: tame_point = wild_point
        # Therefore: (tame_start + tame_distance) * G = wild_distance * wild_start_point
        # Solving for wild_start_point's private key

        private_key = (tame_start + tame.distance - wild.distance) % N

        # Verify the solution
        computed_point = public_key_from_private(private_key)

        if computed_point != wild_start_point:
            raise ValueError("ECDLP solution verification failed")

        return private_key


def calculate_optimal_dp_bits(range_bits: int) -> int:
    """
    Calculate optimal DP bits for given range size.

    Formula: dp_bits ≈ (range_bits / 2) - 5
    Ensures reasonable memory usage while maintaining efficiency.
    """
    dp_bits = max(20, min(32, (range_bits // 2) - 5))
    return dp_bits


# Test the DP system
def test_dp_system():
    """Test distinguished point detection and storage."""
    from .secp256k1 import G, point_multiply

    # Test DP detection
    test_point = Point(0x1000000000000000000000000000000000000000000000000000000000000000,
                      0x2000000000000000000000000000000000000000000000000000000000000000)

    # This point has many trailing zeros - should be distinguished
    assert is_distinguished(test_point, 20), "Point should be distinguished with 20 bits"
    assert not is_distinguished(G, 20), "Generator should not be distinguished"

    # Test DP database (requires Redis)
    try:
        db = DPDatabase()
        db.clear_all()

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
        assert stats["total_dps"] >= 2

        print("✅ Distinguished point system tests passed")

    except redis.ConnectionError:
        print("⚠️  Redis not available - skipping database tests")


if __name__ == "__main__":
    test_dp_system()