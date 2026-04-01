"""Host and runtime metadata capture for benchmark reproducibility."""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


def _safe_mb(value_bytes: Any) -> float | None:
    """Convert bytes to MB when the input is numeric."""
    if not isinstance(value_bytes, (int, float)):
        return None
    return round(float(value_bytes) / (1024 * 1024), 2)


def _safe_command_output(command: list[str]) -> str:
    """Run a command and return the first non-empty output line."""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    combined = "\n".join(
        part for part in (completed.stdout.strip(), completed.stderr.strip()) if part
    )
    for line in combined.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _collect_docker_info(docker_manager: Any) -> dict[str, Any]:
    """Collect Docker daemon metadata if available."""
    if docker_manager is None or not hasattr(docker_manager, "client"):
        return {}

    version = ""
    try:
        version_info = docker_manager.client.version()
        if isinstance(version_info, dict):
            version = str(version_info.get("Version", "") or "")
    except Exception:
        version = ""

    try:
        info = docker_manager.client.info()
    except Exception:
        info = {}

    if not isinstance(info, dict):
        info = {}

    return {
        "server_version": version or info.get("ServerVersion") or info.get("ServerVersion".lower()),
        "operating_system": info.get("OperatingSystem"),
        "architecture": info.get("Architecture"),
        "engine_cpus": info.get("NCPU"),
        "engine_memory_mb": _safe_mb(info.get("MemTotal")),
        "driver": info.get("Driver"),
    }


def _collect_container_metadata(docker_manager: Any, container_name: str) -> dict[str, Any]:
    """Collect runtime limits for the benchmark target container."""
    if docker_manager is None or not container_name:
        return {}

    try:
        container = docker_manager.get_container(container_name)
        attrs = getattr(container, "attrs", None)
    except Exception:
        return {"name": container_name}

    if not isinstance(attrs, dict):
        return {"name": container_name}

    host_config = attrs.get("HostConfig", {})
    config = attrs.get("Config", {})

    nano_cpus = host_config.get("NanoCpus", 0) or 0
    cpu_quota = host_config.get("CpuQuota", 0) or 0
    cpu_period = host_config.get("CpuPeriod", 0) or 0
    cpu_limit = None
    if nano_cpus:
        cpu_limit = round(float(nano_cpus) / 1_000_000_000, 3)
    elif cpu_quota > 0 and cpu_period > 0:
        cpu_limit = round(float(cpu_quota) / float(cpu_period), 3)

    return {
        "name": attrs.get("Name", "").lstrip("/") or container_name,
        "image": config.get("Image"),
        "cpus": cpu_limit,
        "cpuset_cpus": host_config.get("CpusetCpus") or "",
        "memory_limit_mb": _safe_mb(host_config.get("Memory")),
    }


def collect_environment_snapshot(
    docker_manager: Any = None,
    ycsb_runner: Any = None,
    container_name: str = "",
) -> dict[str, Any]:
    """Collect host/runtime metadata for benchmark reproducibility."""
    java_executable = ""
    java_version = ""
    ycsb_path = ""

    if ycsb_runner is not None:
        ycsb_path = str(getattr(ycsb_runner, "ycsb_path", "") or "")
        try:
            java_executable = ycsb_runner._get_java_executable()
        except Exception:
            java_executable = ""
        if java_executable:
            java_version = _safe_command_output([java_executable, "-version"])

    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": {
            "hostname": socket.gethostname(),
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
        },
        "runtime": {
            "python_version": sys.version.split()[0],
            "python_executable": sys.executable,
            "java_executable": java_executable,
            "java_version": java_version,
            "ycsb_path": ycsb_path,
        },
        "docker": _collect_docker_info(docker_manager),
        "target_container": _collect_container_metadata(docker_manager, container_name),
    }
