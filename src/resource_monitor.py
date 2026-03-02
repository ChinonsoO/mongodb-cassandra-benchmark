"""Background Docker container resource monitoring.

Collects CPU, memory, disk I/O, and network metrics from
Docker containers at regular intervals during benchmark runs.
"""

import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """Monitor Docker container resource utilization in a background thread.

    Periodically polls Docker container stats and stores snapshots
    for later analysis. Designed to run concurrently with YCSB benchmarks.
    """

    def __init__(
        self,
        container_name: str,
        docker_client: Any = None,
        interval: float = 1.0,
    ):
        """Initialize ResourceMonitor.

        Args:
            container_name: Name of the Docker container to monitor.
            docker_client: Docker client instance (lazy-created if None).
            interval: Seconds between resource samples.
        """
        self.container_name = container_name
        self._docker_client = docker_client
        self.interval = interval
        self._samples: list[dict[str, Any]] = []
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def docker_client(self) -> Any:
        """Lazy-initialize Docker client."""
        if self._docker_client is None:
            import docker
            self._docker_client = docker.from_env()
        return self._docker_client

    def start(self) -> None:
        """Start the background monitoring thread.

        Raises:
            RuntimeError: If already running.
        """
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("ResourceMonitor is already running")

        self._samples = []
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name=f"resource-monitor-{self.container_name}",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"Resource monitoring started for '{self.container_name}'")

    def stop(self) -> list[dict[str, Any]]:
        """Stop the monitoring thread and return collected samples.

        Returns:
            List of resource sample dictionaries.
        """
        if self._thread is None:
            return self._samples

        self._stop_event.set()
        self._thread.join(timeout=10)
        self._thread = None

        logger.info(
            f"Resource monitoring stopped for '{self.container_name}' "
            f"({len(self._samples)} samples collected)"
        )
        return list(self._samples)

    def get_samples(self) -> list[dict[str, Any]]:
        """Get a copy of collected samples so far.

        Returns:
            List of resource sample dictionaries.
        """
        return list(self._samples)

    def _monitor_loop(self) -> None:
        """Background monitoring loop that polls Docker stats."""
        try:
            container = self.docker_client.containers.get(self.container_name)
        except Exception as e:
            logger.error(f"Could not find container '{self.container_name}': {e}")
            return

        while not self._stop_event.is_set():
            try:
                stats = container.stats(stream=False)
                sample = self._parse_stats(stats)
                self._samples.append(sample)
            except Exception as e:
                logger.warning(f"Failed to collect stats: {e}")

            self._stop_event.wait(self.interval)

    @staticmethod
    def _parse_stats(stats: dict[str, Any]) -> dict[str, Any]:
        """Parse raw Docker stats into a structured sample.

        Args:
            stats: Raw Docker stats dictionary from container.stats().

        Returns:
            Parsed sample with cpu_percent, mem_usage_mb, etc.
        """
        sample: dict[str, Any] = {"timestamp": time.time()}

        # CPU calculation
        cpu_percent = _calculate_cpu_percent(stats)
        sample["cpu_percent"] = cpu_percent

        # Memory
        mem_stats = stats.get("memory_stats", {})
        mem_usage = mem_stats.get("usage", 0)
        mem_limit = mem_stats.get("limit", 1)
        sample["mem_usage_mb"] = mem_usage / (1024 * 1024)
        sample["mem_limit_mb"] = mem_limit / (1024 * 1024)
        sample["mem_percent"] = (mem_usage / mem_limit * 100) if mem_limit > 0 else 0

        # Block I/O
        blk_read, blk_write = _calculate_blkio(stats)
        sample["blk_read_mb"] = blk_read / (1024 * 1024)
        sample["blk_write_mb"] = blk_write / (1024 * 1024)

        # Network I/O
        net_rx, net_tx = _calculate_network(stats)
        sample["net_rx_mb"] = net_rx / (1024 * 1024)
        sample["net_tx_mb"] = net_tx / (1024 * 1024)

        return sample


def _calculate_cpu_percent(stats: dict[str, Any]) -> float:
    """Calculate CPU utilization percentage from Docker stats.

    Args:
        stats: Raw Docker stats dictionary.

    Returns:
        CPU usage as a percentage.
    """
    cpu_stats = stats.get("cpu_stats", {})
    precpu_stats = stats.get("precpu_stats", {})

    cpu_total = cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
    precpu_total = precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
    cpu_delta = cpu_total - precpu_total

    system_total = cpu_stats.get("system_cpu_usage", 0)
    presystem_total = precpu_stats.get("system_cpu_usage", 0)
    system_delta = system_total - presystem_total

    num_cpus = cpu_stats.get("online_cpus", 1)

    if system_delta > 0 and cpu_delta >= 0:
        return (cpu_delta / system_delta) * num_cpus * 100.0
    return 0.0


def _calculate_blkio(stats: dict[str, Any]) -> tuple[int, int]:
    """Calculate block I/O bytes from Docker stats.

    Args:
        stats: Raw Docker stats dictionary.

    Returns:
        Tuple of (read_bytes, write_bytes).
    """
    blkio = stats.get("blkio_stats", {})
    io_bytes = blkio.get("io_service_bytes_recursive", None)

    if not io_bytes:
        return 0, 0

    read_bytes = 0
    write_bytes = 0
    for entry in io_bytes:
        op = entry.get("op", "").lower()
        value = entry.get("value", 0)
        if op == "read":
            read_bytes += value
        elif op == "write":
            write_bytes += value

    return read_bytes, write_bytes


def _calculate_network(stats: dict[str, Any]) -> tuple[int, int]:
    """Calculate network I/O bytes from Docker stats.

    Args:
        stats: Raw Docker stats dictionary.

    Returns:
        Tuple of (rx_bytes, tx_bytes).
    """
    networks = stats.get("networks", {})
    rx_bytes = sum(v.get("rx_bytes", 0) for v in networks.values())
    tx_bytes = sum(v.get("tx_bytes", 0) for v in networks.values())
    return rx_bytes, tx_bytes
