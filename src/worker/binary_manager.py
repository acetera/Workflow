"""
Binary management for RCKangaroo executable.
Handles downloading, verification, and caching of the binary.
"""

import os
import hashlib
import subprocess
from typing import Optional
from pathlib import Path
import requests


class BinaryManager:
    """Manages RCKangaroo binary acquisition and verification."""

    def __init__(self, binary_dir: str = "/app/binaries"):
        self.binary_dir = Path(binary_dir)
        self.binary_dir.mkdir(exist_ok=True)
        self.binary_path = self.binary_dir / "RCKangaroo"

    def get_binary_path(self) -> str:
        """Get path to RCKangaroo binary, downloading if necessary."""
        if not self.binary_path.exists():
            self._acquire_binary()

        if not self._verify_binary():
            raise RuntimeError("Binary verification failed")

        return str(self.binary_path)

    def _acquire_binary(self):
        """Acquire RCKangaroo binary using best available method."""

        # Method 1: Check if provided via environment variable
        binary_url = os.getenv("RCKANG_BINARY_URL")
        if binary_url:
            print(f"Downloading RCKangaroo from: {binary_url}")
            self._download_binary(binary_url)
            return

        # Method 2: Check if provided via mounted volume
        mounted_binary = Path("/binaries/RCKangaroo")
        if mounted_binary.exists():
            print("Using mounted RCKangaroo binary")
            import shutil
            shutil.copy2(mounted_binary, self.binary_path)
            return

        # Method 3: Build from source
        print("Building RCKangaroo from source...")
        self._build_from_source()

    def _download_binary(self, url: str):
        """Download binary from URL."""
        response = requests.get(url, stream=True)
        response.raise_for_status()

        with open(self.binary_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        os.chmod(self.binary_path, 0o755)

    def _build_from_source(self):
        """Build RCKangaroo from source code."""
        build_dir = Path("/tmp/rckang_build")
        build_dir.mkdir(exist_ok=True)

        # Clone repository
        subprocess.run([
            "git", "clone",
            "https://github.com/RetiredC/RCKangaroo.git",
            str(build_dir)
        ], check=True)

        # Build
        subprocess.run([
            "make", "gpu=1", f"CUDA=/usr/local/cuda"
        ], cwd=build_dir, check=True)

        # Copy binary
        built_binary = build_dir / "RCKangaroo"
        import shutil
        shutil.copy2(built_binary, self.binary_path)
        os.chmod(self.binary_path, 0o755)

    def _verify_binary(self) -> bool:
        """Verify binary is executable and working."""
        try:
            # Check if file is executable
            if not os.access(self.binary_path, os.X_OK):
                return False

            # Try to run with help flag
            result = subprocess.run([
                str(self.binary_path), "-h"
            ], capture_output=True, timeout=10)

            # RCKangaroo should show help or usage info
            return result.returncode == 0 or "usage" in result.stderr.decode().lower()

        except Exception as e:
            print(f"Binary verification failed: {e}")
            return False

    def get_binary_info(self) -> dict:
        """Get information about the binary."""
        if not self.binary_path.exists():
            return {"status": "not_found"}

        # Get file hash for verification
        with open(self.binary_path, 'rb') as f:
            binary_hash = hashlib.sha256(f.read()).hexdigest()

        # Get file size
        file_size = self.binary_path.stat().st_size

        return {
            "status": "available",
            "path": str(self.binary_path),
            "size_bytes": file_size,
            "sha256": binary_hash,
            "executable": os.access(self.binary_path, os.X_OK)
        }


# Global binary manager instance
binary_manager = BinaryManager()


def get_rckang_path() -> str:
    """Get path to RCKangaroo binary."""
    return binary_manager.get_binary_path()


def verify_rckang_available() -> bool:
    """Verify RCKangaroo is available and working."""
    try:
        path = get_rckang_path()
        return binary_manager._verify_binary()
    except Exception:
        return False