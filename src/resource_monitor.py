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

        container_attrs = getattr(container, "attrs", {})
        if not isinstance(container_attrs, dict):
            try:
                container.reload()
                container_attrs = getattr(container, "attrs", {})
            except Exception:
                container_attrs = {}

        while not self._stop_event.is_set():
            try:
                stats = container.stats(stream=False)
                cpu_budget = _calculate_cpu_budget(stats, container_attrs)
                sample = self._parse_stats(stats, cpu_budget=cpu_budget)
                self._samples.append(sample)
            except Exception as e:
                logger.warning(f"Failed to collect stats: {e}")

            self._stop_event.wait(self.interval)

    @staticmethod
    def _parse_stats(
        stats: dict[str, Any],
        cpu_budget: float | None = None,
    ) -> dict[str, Any]:
        """Parse raw Docker stats into a structured sample.

        Args:
            stats: Raw Docker stats dictionary from container.stats().
            cpu_budget: Effective CPU budget for the container. When omitted,
                falls back to Docker's visible CPU count.

        Returns:
            Parsed sample with cpu_percent, mem_usage_mb, etc.
        """
        sample: dict[str, Any] = {"timestamp": time.time()}

        # Normalize Docker's multi-core CPU percentage against the
        # container's allowed CPU budget rather than host-visible CPUs.
        cpu_percent = _calculate_cpu_percent(stats)
        effective_budget = cpu_budget or _calculate_cpu_budget(stats)
        sample["cpu_percent"] = cpu_percent / effective_budget

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


def _calculate_cpu_budget(
    stats: dict[str, Any],
    container_attrs: dict[str, Any] | None = None,
) -> float:
    """Determine the effective CPU budget available to a container.

    Prefers explicit runtime limits from Docker container config. Falls back
    to Docker's reported online CPU count when no quota/pinning is set.
    """
    candidates: list[float] = []

    if isinstance(container_attrs, dict):
        host_config = container_attrs.get("HostConfig", {})
        if isinstance(host_config, dict):
            nano_cpus = host_config.get("NanoCpus", 0) or 0
            if nano_cpus > 0:
                candidates.append(float(nano_cpus) / 1_000_000_000)

            cpu_quota = host_config.get("CpuQuota", 0) or 0
            cpu_period = host_config.get("CpuPeriod", 0) or 0
            if cpu_quota > 0 and cpu_period > 0:
                candidates.append(float(cpu_quota) / float(cpu_period))

            cpuset_cpus = _count_cpuset_cpus(host_config.get("CpusetCpus", ""))
            if cpuset_cpus > 0:
                candidates.append(float(cpuset_cpus))

    online_cpus = stats.get("cpu_stats", {}).get("online_cpus", 1) or 1
    if online_cpus > 0:
        candidates.append(float(online_cpus))

    positive = [c for c in candidates if c > 0]
    return min(positive) if positive else 1.0


def _count_cpuset_cpus(cpuset: str) -> int:
    """Count CPUs described by a cpuset string like '0-1,4,6-7'."""
    if not cpuset:
        return 0

    total = 0
    for part in cpuset.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            try:
                start = int(start_text)
                end = int(end_text)
            except ValueError:
                continue
            if end >= start:
                total += end - start + 1
        else:
            try:
                int(token)
            except ValueError:
                continue
            total += 1
    return total


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
