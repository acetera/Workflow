"""
CPU-based kangaroo implementation for testing and validation.
Uses the same algorithms as RCKangaroo but runs on CPU.
"""

import random
from typing import Tuple, Optional, List
from datetime import datetime

from .secp256k1 import Point, G, point_multiply, point_add
from .distinguished_point import DistinguishedPoint, is_distinguished


class CPUKangaroo:
    """CPU implementation of Pollard's kangaroo algorithm."""

    def __init__(self, dp_bits: int = 20):
        """
        Initialize kangaroo solver.

        Args:
            dp_bits: Number of trailing zero bits for distinguished points
        """
        self.dp_bits = dp_bits
        self.jump_table = self._generate_jump_table()

    def _generate_jump_table(self, table_size: int = 256) -> List[Tuple[int, Point]]:
        """Generate jump table for pseudorandom walks."""
        table = []
        for i in range(table_size):
            # Use deterministic jumps based on point x-coordinate
            jump_size = 1 + (i % 32)  # Jump sizes from 1 to 32
            jump_point = point_multiply(G, jump_size)
            table.append((jump_size, jump_point))
        return table

    def _get_jump(self, point: Point) -> Tuple[int, Point]:
        """Get pseudorandom jump based on point coordinates."""
        # Use lower bits of x-coordinate to index jump table
        index = point.x & 0xFF  # Lower 8 bits
        return self.jump_table[index]

    def tame_walk(
        self,
        start_key: int,
        target_point: Point,
        max_steps: int = 1000000
    ) -> List[DistinguishedPoint]:
        """
        Perform tame kangaroo walk.

        Args:
            start_key: Starting private key
            target_point: Target public key point
            max_steps: Maximum steps before giving up

        Returns:
            List of distinguished points found
        """
        distinguished_points = []
        current_key = start_key
        current_point = point_multiply(G, current_key)

        for step in range(max_steps):
            # Check if current point is distinguished
            if is_distinguished(current_point, self.dp_bits):
                dp = DistinguishedPoint(
                    x=current_point.x,
                    y=current_point.y,
                    walk_type="tame",
                    distance=current_key - start_key,
                    worker_id="cpu_tame",
                    timestamp=datetime.now().timestamp()
                )
                distinguished_points.append(dp)

            # Make pseudorandom jump
            jump_size, jump_point = self._get_jump(current_point)
            current_key += jump_size
            current_point = point_add(current_point, jump_point)

            # Check if we've reached the target (extremely unlikely but possible)
            if current_point.x == target_point.x and current_point.y == target_point.y:
                print(f"🎉 Tame walk found solution: {hex(current_key)}")
                return distinguished_points

        return distinguished_points

    def wild_walk(
        self,
        target_point: Point,
        max_steps: int = 1000000
    ) -> List[DistinguishedPoint]:
        """
        Perform wild kangaroo walk.

        Args:
            target_point: Target public key point
            max_steps: Maximum steps before giving up

        Returns:
            List of distinguished points found
        """
        distinguished_points = []
        distance = 0
        current_point = target_point

        for step in range(max_steps):
            # Check if current point is distinguished
            if is_distinguished(current_point, self.dp_bits):
                dp = DistinguishedPoint(
                    x=current_point.x,
                    y=current_point.y,
                    walk_type="wild",
                    distance=distance,
                    worker_id="cpu_wild",
                    timestamp=datetime.now().timestamp()
                )
                distinguished_points.append(dp)

            # Make pseudorandom jump
            jump_size, jump_point = self._get_jump(current_point)
            distance += jump_size
            current_point = point_add(current_point, jump_point)

        return distinguished_points

    def solve_range(
        self,
        start_key: int,
        end_key: int,
        target_point: Point,
        max_steps_per_walk: int = 100000
    ) -> Optional[int]:
        """
        Attempt to solve ECDLP in given range using kangaroo method.

        Args:
            start_key: Start of search range
            end_key: End of search range
            target_point: Target public key
            max_steps_per_walk: Max steps per kangaroo walk

        Returns:
            Private key if found, None otherwise
        """
        from .memory_dp_database import MemoryDPDatabase
        from .distinguished_point import CollisionResult

        # Use local DP database for this solve attempt
        dp_db = MemoryDPDatabase()

        # Calculate range midpoint for tame start
        range_size = end_key - start_key
        tame_start = start_key + (range_size // 2)

        print(f"Solving range [{hex(start_key)}, {hex(end_key)}]")
        print(f"Range size: 2^{range_size.bit_length()} keys")
        print(f"Tame start: {hex(tame_start)}")
        print(f"DP bits: {self.dp_bits}")

        # Start both walks concurrently (simulated)
        max_iterations = 10
        for iteration in range(max_iterations):
            print(f"Iteration {iteration + 1}/{max_iterations}")

            # Tame walk
            tame_dps = self.tame_walk(tame_start, target_point, max_steps_per_walk)
            for dp in tame_dps:
                collision = dp_db.store_dp(dp)
                if collision:
                    print("🎉 Collision found in tame walk!")
                    return self._solve_from_collision(collision, tame_start, target_point)

            # Wild walk
            wild_dps = self.wild_walk(target_point, max_steps_per_walk)
            for dp in wild_dps:
                collision = dp_db.store_dp(dp)
                if collision:
                    print("🎉 Collision found in wild walk!")
                    return self._solve_from_collision(collision, tame_start, target_point)

            # Progress update
            stats = dp_db.get_stats()
            print(f"  DPs found: {stats['total_dps']} (tame: {stats['dps_tame']}, wild: {stats['dps_wild']})")

        print("No collision found within step limit")
        return None

    def _solve_from_collision(
        self,
        collision: 'CollisionResult',
        tame_start: int,
        target_point: Point
    ) -> int:
        """Solve ECDLP from collision."""
        try:
            private_key = collision.solve_ecdlp(tame_start, target_point)
            print(f"🔑 Private key found: {hex(private_key)}")
            return private_key
        except Exception as e:
            print(f"❌ Error solving ECDLP: {e}")
            return None


def test_cpu_kangaroo():
    """Test CPU kangaroo implementation with known solution."""
    from .secp256k1 import public_key_from_private

    # Test with a small known private key
    test_private_key = 0x12345
    test_public_key = public_key_from_private(test_private_key)

    # Create search range around the target
    range_start = test_private_key - 1000
    range_end = test_private_key + 1000

    kangaroo = CPUKangaroo(dp_bits=12)  # Lower DP bits for faster testing

    print("Testing CPU Kangaroo with known solution...")
    print(f"Target private key: {hex(test_private_key)}")
    print(f"Target public key: ({hex(test_public_key.x)}, {hex(test_public_key.y)})")

    solution = kangaroo.solve_range(range_start, range_end, test_public_key, max_steps_per_walk=10000)

    if solution == test_private_key:
        print("✅ CPU Kangaroo test passed!")
        return True
    else:
        print(f"❌ CPU Kangaroo test failed. Expected {hex(test_private_key)}, got {hex(solution) if solution else 'None'}")
        return False


if __name__ == "__main__":
    test_cpu_kangaroo()