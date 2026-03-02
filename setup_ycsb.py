"""Download and set up YCSB 0.17.0 for benchmarking.

Downloads the YCSB release tarball from GitHub and extracts it
to the project directory. Verifies Java availability.
"""

import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

YCSB_VERSION = "0.17.0"
YCSB_URL = (
    f"https://github.com/brianfrankcooper/YCSB/releases/download/"
    f"{YCSB_VERSION}/ycsb-{YCSB_VERSION}.tar.gz"
)
YCSB_DIR = f"ycsb-{YCSB_VERSION}"
YCSB_TARBALL = f"ycsb-{YCSB_VERSION}.tar.gz"


def check_java() -> bool:
    """Check if Java is available on the system.

    Returns:
        True if Java is installed and accessible.
    """
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Java outputs version info to stderr
        version_output = result.stderr or result.stdout
        print(f"Java found: {version_output.strip().splitlines()[0]}")
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def download_ycsb(url: str = YCSB_URL, output: str = YCSB_TARBALL) -> str:
    """Download the YCSB release tarball.

    Args:
        url: URL to download from.
        output: Local filename to save the tarball.

    Returns:
        Path to the downloaded file.

    Raises:
        RuntimeError: If download fails.
    """
    output_path = Path(output)

    if output_path.exists():
        print(f"YCSB tarball already exists: {output}")
        return output

    print(f"Downloading YCSB {YCSB_VERSION} from {url}...")
    print("This may take a few minutes (file is ~675 MB)...")

    try:
        urllib.request.urlretrieve(url, output, reporthook=_download_progress)
        print(f"\nDownload complete: {output}")
        return output
    except Exception as e:
        # Clean up partial download
        if output_path.exists():
            output_path.unlink()
        raise RuntimeError(f"Failed to download YCSB: {e}") from e


def extract_ycsb(tarball: str = YCSB_TARBALL, target_dir: str = ".") -> str:
    """Extract the YCSB tarball.

    Args:
        tarball: Path to the YCSB tarball.
        target_dir: Directory to extract into.

    Returns:
        Path to the extracted YCSB directory.

    Raises:
        RuntimeError: If extraction fails.
    """
    ycsb_path = Path(target_dir) / YCSB_DIR

    if ycsb_path.exists():
        print(f"YCSB directory already exists: {ycsb_path}")
        return str(ycsb_path)

    print(f"Extracting {tarball}...")

    try:
        with tarfile.open(tarball, "r:gz") as tar:
            tar.extractall(path=target_dir)
        print(f"Extraction complete: {ycsb_path}")
        return str(ycsb_path)
    except Exception as e:
        raise RuntimeError(f"Failed to extract YCSB: {e}") from e


def verify_ycsb(ycsb_path: str = YCSB_DIR) -> bool:
    """Verify the YCSB installation is complete.

    Args:
        ycsb_path: Path to the YCSB directory.

    Returns:
        True if all expected files/directories exist.
    """
    ycsb_path = Path(ycsb_path)

    # Check for executable
    if platform.system() == "Windows":
        executable = ycsb_path / "bin" / "ycsb.bat"
    else:
        executable = ycsb_path / "bin" / "ycsb"

    checks = {
        "YCSB directory": ycsb_path.exists(),
        "YCSB executable": executable.exists(),
        "Workloads directory": (ycsb_path / "workloads").exists(),
        "Lib directory": (ycsb_path / "lib").exists(),
    }

    all_ok = True
    for name, passed in checks.items():
        status = "OK" if passed else "MISSING"
        print(f"  {name}: {status}")
        if not passed:
            all_ok = False

    return all_ok


def _download_progress(count: int, block_size: int, total_size: int) -> None:
    """Report download progress."""
    if total_size > 0:
        percent = min(100, count * block_size * 100 // total_size)
        mb_done = count * block_size / (1024 * 1024)
        mb_total = total_size / (1024 * 1024)
        print(f"\r  Progress: {percent}% ({mb_done:.1f}/{mb_total:.1f} MB)", end="")
    else:
        mb_done = count * block_size / (1024 * 1024)
        print(f"\r  Downloaded: {mb_done:.1f} MB", end="")


def main() -> int:
    """Main setup workflow.

    Returns:
        Exit code (0 for success).
    """
    print("=" * 50)
    print(f"  YCSB {YCSB_VERSION} Setup")
    print("=" * 50)

    # Step 1: Check Java
    print("\n[1/3] Checking Java installation...")
    if not check_java():
        print("ERROR: Java not found!")
        print("YCSB requires Java 8 or 11. Please install Java and try again.")
        print("Download: https://adoptium.net/")
        return 1

    # Step 2: Download
    print(f"\n[2/3] Downloading YCSB {YCSB_VERSION}...")
    try:
        tarball = download_ycsb()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    # Step 3: Extract
    print(f"\n[3/3] Extracting YCSB...")
    try:
        ycsb_path = extract_ycsb(tarball)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    # Verify
    print("\nVerifying installation:")
    if verify_ycsb(ycsb_path):
        print(f"\nYCSB {YCSB_VERSION} is ready!")
        print(f"Installation path: {Path(ycsb_path).resolve()}")
        return 0
    else:
        print("\nWARNING: YCSB installation may be incomplete.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
