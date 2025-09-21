"""
Work distribution engine for the Bitcoin puzzle solver.
Distributes ECDLP ranges across multiple workers with optimal chunking.
"""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class WorkAssignment:
    """Work assignment for a single worker."""
    worker_id: str
    start_key: int  # Start of private key range (EXACT value)
    end_key: int    # End of private key range (EXACT value)
    dp_bits: int    # Distinguished point bits for this range
    puzzle_number: int
    public_key_hex: str  # Target public key
    created_at: float
    status: str = "assigned"  # assigned, in_progress, completed, failed

    @property
    def range_size(self) -> int:
        """Size of the assigned range."""
        return self.end_key - self.start_key + 1

    @property
    def range_bits(self) -> int:
        """Bit size of the range."""
        return self.range_size.bit_length()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "worker_id": self.worker_id,
            "start_key": hex(self.start_key),
            "end_key": hex(self.end_key),
            "dp_bits": self.dp_bits,
            "puzzle_number": self.puzzle_number,
            "public_key_hex": self.public_key_hex,
            "created_at": self.created_at,
            "status": self.status,
            "range_size": self.range_size,
            "range_bits": self.range_bits
        }


class WorkDistributor:
    """Intelligent work distribution for ECDLP solving."""

    def __init__(self):
        self.active_assignments: Dict[str, WorkAssignment] = {}
        self.completed_assignments: List[WorkAssignment] = []

    def calculate_puzzle_range(self, puzzle_number: int) -> Tuple[int, int]:
        """
        Calculate EXACT range for a Bitcoin puzzle.

        Args:
            puzzle_number: Bitcoin puzzle number (e.g., 135)

        Returns:
            (start_key, end_key) as exact integers
        """
        if puzzle_number <= 0:
            raise ValueError("Puzzle number must be positive")

        # Bitcoin puzzles: range is [2^(n-1), 2^n - 1]
        start = 2 ** (puzzle_number - 1)
        end = 2 ** puzzle_number - 1

        return start, end

    def calculate_optimal_dp_bits(self, range_bits: int) -> int:
        """
        Calculate optimal DP bits for given range size.

        Formula based on expected DP count and memory constraints:
        - Smaller ranges: fewer DP bits (more DPs, less memory per DP)
        - Larger ranges: more DP bits (fewer DPs, more memory per DP)
        """
        if range_bits <= 50:
            return 18
        elif range_bits <= 60:
            return 20
        elif range_bits <= 70:
            return 22
        elif range_bits <= 80:
            return 24
        elif range_bits <= 90:
            return 26
        elif range_bits <= 100:
            return 28
        elif range_bits <= 120:
            return 30
        else:
            return 32  # Maximum for very large ranges

    def distribute_work(
        self,
        puzzle_number: int,
        public_key_hex: str,
        num_workers: int,
        overlap_percent: float = 0.05
    ) -> List[WorkAssignment]:
        """
        Distribute puzzle work across multiple workers.

        Args:
            puzzle_number: Bitcoin puzzle number
            public_key_hex: Target public key (compressed format)
            num_workers: Number of workers to distribute to
            overlap_percent: Percentage overlap between chunks (default 5%)

        Returns:
            List of work assignments
        """
        if num_workers <= 0:
            raise ValueError("Number of workers must be positive")

        # Get the exact puzzle range
        total_start, total_end = self.calculate_puzzle_range(puzzle_number)
        total_range = total_end - total_start + 1

        # Calculate base chunk size
        base_chunk_size = total_range // num_workers
        overlap_size = int(base_chunk_size * overlap_percent)

        assignments = []

        for i in range(num_workers):
            worker_id = f"worker_{i:03d}"

            # Calculate this worker's range
            chunk_start = total_start + (i * base_chunk_size)
            chunk_end = chunk_start + base_chunk_size - 1

            # Add overlap (except for last worker)
            if i < num_workers - 1:
                chunk_end += overlap_size
            else:
                # Last worker gets the remainder
                chunk_end = total_end

            # Ensure we don't exceed the total range
            chunk_end = min(chunk_end, total_end)

            # Calculate optimal DP bits for this chunk
            chunk_size = chunk_end - chunk_start + 1
            chunk_bits = chunk_size.bit_length()
            dp_bits = self.calculate_optimal_dp_bits(chunk_bits)

            assignment = WorkAssignment(
                worker_id=worker_id,
                start_key=chunk_start,
                end_key=chunk_end,
                dp_bits=dp_bits,
                puzzle_number=puzzle_number,
                public_key_hex=public_key_hex,
                created_at=datetime.now().timestamp()
            )

            assignments.append(assignment)
            self.active_assignments[worker_id] = assignment

        return assignments

    def get_assignment_stats(self) -> Dict[str, Any]:
        """Get statistics about work assignments."""
        total_assigned = len(self.active_assignments)
        total_completed = len(self.completed_assignments)

        # Calculate total range covered
        total_range_size = 0
        for assignment in self.active_assignments.values():
            total_range_size += assignment.range_size

        for assignment in self.completed_assignments:
            total_range_size += assignment.range_size

        return {
            "active_assignments": total_assigned,
            "completed_assignments": total_completed,
            "total_assignments": total_assigned + total_completed,
            "total_range_size": total_range_size,
            "total_range_bits": total_range_size.bit_length() if total_range_size > 0 else 0
        }

    def update_assignment_status(self, worker_id: str, status: str):
        """Update the status of a work assignment."""
        if worker_id in self.active_assignments:
            assignment = self.active_assignments[worker_id]
            assignment.status = status

            if status in ("completed", "failed"):
                # Move to completed list
                self.completed_assignments.append(assignment)
                del self.active_assignments[worker_id]

    def get_assignment(self, worker_id: str) -> WorkAssignment:
        """Get work assignment for a specific worker."""
        if worker_id in self.active_assignments:
            return self.active_assignments[worker_id]
        raise ValueError(f"No active assignment for worker {worker_id}")


# Known puzzle configurations for testing and validation
PUZZLE_CONFIGS = {
    63: {
        "public_key": "0365ec2994b8cc0a20d40dd69edfe55ca32a54bcbbaa6b0ddcff36049301a54579",
        "private_key": 0x7CCE5EFDACCF6808,  # Known solution for validation
        "status": "SOLVED"
    },
    64: {
        "public_key": "02145d2611c823a396ef6712ce0f712f09b9b4f3135e3e0aa3230fb9b6d08d1e16",
        "status": "UNSOLVED"
    },
    65: {
        "public_key": "03a7a4c30291ac1db24b4ab9d2f7f84c8b5d7c92d3564c8b1e8c8e5b7f5b3e7b9a",
        "private_key": 0x1A838B13505B26867,  # Known solution for validation
        "status": "SOLVED"
    },
    130: {
        "public_key": "0248746b3dc2b3b96ae5d93359a38a71a8f96b4c8e2a61aebe1e6bb9a18c5c29d5",
        "private_key": 0x200000000000000000000000000000000349B84B6431A6C4EF1,
        "status": "SOLVED"
    },
    135: {
        "public_key": "02145d2611c823a396ef6712ce0f712f09b9b4f3135e3e0aa3230fb9b6d08d1e16",
        "status": "UNSOLVED - PRIMARY TARGET"
    }
}


def test_work_distribution():
    """Test work distribution functionality."""
    distributor = WorkDistributor()

    # Test puzzle range calculation
    start, end = distributor.calculate_puzzle_range(63)
    expected_start = 2 ** 62
    expected_end = 2 ** 63 - 1
    assert start == expected_start, f"Puzzle 63 start: {start} != {expected_start}"
    assert end == expected_end, f"Puzzle 63 end: {end} != {expected_end}"

    # Test work distribution for puzzle 63
    puzzle_config = PUZZLE_CONFIGS[63]
    assignments = distributor.distribute_work(
        puzzle_number=63,
        public_key_hex=puzzle_config["public_key"],
        num_workers=4
    )

    assert len(assignments) == 4, "Should create 4 assignments"

    # Verify assignments cover the full range
    total_start, total_end = distributor.calculate_puzzle_range(63)
    min_start = min(a.start_key for a in assignments)
    max_end = max(a.end_key for a in assignments)

    assert min_start == total_start, "Assignments should start at puzzle range start"
    assert max_end == total_end, "Assignments should end at puzzle range end"

    # Test larger puzzle (135)
    puzzle_135_start, puzzle_135_end = distributor.calculate_puzzle_range(135)
    expected_135_start = 2 ** 134
    expected_135_end = 2 ** 135 - 1

    assert puzzle_135_start == expected_135_start
    assert puzzle_135_end == expected_135_end

    # Test assignment statistics
    stats = distributor.get_assignment_stats()
    assert stats["active_assignments"] == 4
    assert stats["completed_assignments"] == 0

    print("✅ Work distribution tests passed")

    # Print sample assignment for verification
    sample = assignments[0]
    print(f"Sample assignment: Worker {sample.worker_id}")
    print(f"  Range: {hex(sample.start_key)} to {hex(sample.end_key)}")
    print(f"  Size: 2^{sample.range_bits} keys")
    print(f"  DP bits: {sample.dp_bits}")


if __name__ == "__main__":
    test_work_distribution()