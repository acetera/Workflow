"""
secp256k1 elliptic curve operations with EXACT parameters.
NO placeholders, NO approximations - only real cryptographic math.
"""

from typing import Tuple, Optional
from dataclasses import dataclass

# EXACT secp256k1 parameters - these are the ACTUAL values
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F  # Field prime
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141  # Group order
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798  # Generator x
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8  # Generator y


@dataclass
class Point:
    """Elliptic curve point with exact coordinates."""
    x: int
    y: int

    def __post_init__(self):
        """Verify point is on secp256k1 curve."""
        if not self.is_on_curve():
            raise ValueError(f"Point ({hex(self.x)}, {hex(self.y)}) is not on secp256k1 curve")

    def is_on_curve(self) -> bool:
        """Verify y² = x³ + 7 (mod p)"""
        if self.x == 0 and self.y == 0:  # Point at infinity
            return True
        left = (self.y * self.y) % P
        right = (self.x * self.x * self.x + 7) % P
        return left == right

    def __eq__(self, other) -> bool:
        return isinstance(other, Point) and self.x == other.x and self.y == other.y


# Generator point
G = Point(GX, GY)

# Point at infinity
INFINITY = Point(0, 0)


def mod_inverse(a: int, m: int) -> int:
    """Compute modular inverse using extended Euclidean algorithm."""
    if a < 0:
        return mod_inverse(a % m, m)

    def extended_gcd(a: int, b: int) -> Tuple[int, int, int]:
        if a == 0:
            return b, 0, 1
        gcd, x1, y1 = extended_gcd(b % a, a)
        x = y1 - (b // a) * x1
        y = x1
        return gcd, x, y

    gcd, x, _ = extended_gcd(a, m)
    if gcd != 1:
        raise ValueError(f"Modular inverse does not exist for {a} mod {m}")
    return x % m


def point_add(p1: Point, p2: Point) -> Point:
    """Add two points on secp256k1 curve using exact field arithmetic."""
    if p1 == INFINITY:
        return p2
    if p2 == INFINITY:
        return p1
    if p1.x == p2.x:
        if p1.y == p2.y:
            return point_double(p1)
        else:
            return INFINITY

    # Calculate slope: s = (y2 - y1) / (x2 - x1) mod p
    dx = (p2.x - p1.x) % P
    dy = (p2.y - p1.y) % P
    s = (dy * mod_inverse(dx, P)) % P

    # Calculate result: x3 = s² - x1 - x2, y3 = s(x1 - x3) - y1
    x3 = (s * s - p1.x - p2.x) % P
    y3 = (s * (p1.x - x3) - p1.y) % P

    return Point(x3, y3)


def point_double(p: Point) -> Point:
    """Double a point on secp256k1 curve."""
    if p == INFINITY:
        return INFINITY
    if p.y == 0:
        return INFINITY

    # Calculate slope: s = (3x² + a) / (2y) mod p
    # For secp256k1, a = 0, so s = 3x² / 2y
    numerator = (3 * p.x * p.x) % P
    denominator = (2 * p.y) % P
    s = (numerator * mod_inverse(denominator, P)) % P

    # Calculate result: x3 = s² - 2x, y3 = s(x - x3) - y
    x3 = (s * s - 2 * p.x) % P
    y3 = (s * (p.x - x3) - p.y) % P

    return Point(x3, y3)


def point_multiply(point: Point, k: int) -> Point:
    """Multiply point by scalar using double-and-add method."""
    if k == 0:
        return INFINITY
    if k == 1:
        return point
    if k < 0:
        raise ValueError("Scalar multiplication with negative values not supported")

    result = INFINITY
    addend = point

    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_double(addend)
        k >>= 1

    return result


def public_key_from_private(private_key: int) -> Point:
    """Generate public key from private key: pubkey = private_key * G"""
    if not (1 <= private_key < N):
        raise ValueError(f"Private key must be in range [1, {N-1}]")
    return point_multiply(G, private_key)


def compress_point(point: Point) -> bytes:
    """Compress point to 33-byte format (0x02/0x03 + x-coordinate)."""
    if point == INFINITY:
        raise ValueError("Cannot compress point at infinity")

    prefix = 0x02 if point.y % 2 == 0 else 0x03
    x_bytes = point.x.to_bytes(32, 'big')
    return bytes([prefix]) + x_bytes


def decompress_point(compressed: bytes) -> Point:
    """Decompress 33-byte point to full coordinates."""
    if len(compressed) != 33:
        raise ValueError("Compressed point must be 33 bytes")

    prefix = compressed[0]
    if prefix not in (0x02, 0x03):
        raise ValueError("Invalid compression prefix")

    x = int.from_bytes(compressed[1:], 'big')

    # Solve for y: y² = x³ + 7 (mod p)
    y_squared = (x * x * x + 7) % P

    # Find square root
    y = pow(y_squared, (P + 1) // 4, P)

    # Choose correct y based on parity
    if (y % 2) != (prefix - 0x02):
        y = P - y

    return Point(x, y)


# Test vectors for validation
TEST_VECTORS = {
    "generator": {
        "x": GX,
        "y": GY
    },
    "point_double": {
        "input": G,
        "expected_x": 0xC6047F9441ED7D6D3045406E95C07CD85C778E4B8CEF3CA7ABAC09B95C709EE5,
        "expected_y": 0x1AE168FEA63DC339A3C58419466CEAEEF7F632653266D0E1236431A950CFE52A
    },
    "known_puzzle_63": {
        "private_key": 0x7CCE5EFDACCF6808,
        "expected_pubkey_compressed": "0365ec2994b8cc0a20d40dd69edfe55ca32a54bcbbaa6b0ddcff36049301a54579"
    }
}


def validate_implementation() -> bool:
    """Validate implementation against known test vectors."""
    try:
        # Test 1: Generator point is valid
        assert G.is_on_curve(), "Generator point not on curve"

        # Test 2: Point doubling
        doubled = point_double(G)
        expected = TEST_VECTORS["point_double"]
        assert doubled.x == expected["expected_x"], f"Point double x mismatch: {hex(doubled.x)} != {hex(expected['expected_x'])}"
        assert doubled.y == expected["expected_y"], f"Point double y mismatch: {hex(doubled.y)} != {hex(expected['expected_y'])}"

        # Test 3: Known puzzle solution
        puzzle_63 = TEST_VECTORS["known_puzzle_63"]
        pubkey = public_key_from_private(puzzle_63["private_key"])
        compressed = compress_point(pubkey)
        expected_hex = puzzle_63["expected_pubkey_compressed"]
        actual_hex = compressed.hex()
        assert actual_hex == expected_hex, f"Puzzle 63 mismatch: {actual_hex} != {expected_hex}"

        # Test 4: Point decompression
        decompressed = decompress_point(compressed)
        assert decompressed == pubkey, "Point compression/decompression failed"

        print("✅ All secp256k1 test vectors passed")
        return True

    except Exception as e:
        print(f"❌ secp256k1 validation failed: {e}")
        return False


if __name__ == "__main__":
    validate_implementation()