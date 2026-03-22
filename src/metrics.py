"""Statistical metrics computation and aggregation."""

from typing import Any, Optional

import numpy as np


def aggregate_runs(run_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate metrics across multiple repetitions of the same configuration.

    Computes mean and standard deviation for each numeric metric.

    Args:
        run_results: List of metric dictionaries from repeated runs.

    Returns:
        Dictionary with '{metric}_mean' and '{metric}_std' for each numeric metric.

    Raises:
        ValueError: If run_results is empty.
    """
    if not run_results:
        raise ValueError("Cannot aggregate empty list of run results")

    if len(run_results) == 1:
        # Single run - return values directly with zero std
        result = {}
        for key, value in run_results[0].items():
            if isinstance(value, (int, float)):
                result[f"{key}_mean"] = float(value)
                result[f"{key}_std"] = 0.0
            else:
                result[key] = value
        return result

    # Collect all numeric keys
    numeric_keys = set()
    non_numeric = {}
    for run in run_results:
        for key, value in run.items():
            if isinstance(value, (int, float)):
                numeric_keys.add(key)
            else:
                non_numeric[key] = value

    result = dict(non_numeric)

    for key in sorted(numeric_keys):
        values = [
            run[key]
            for run in run_results
            if key in run and isinstance(run[key], (int, float))
        ]
        if values:
            arr = np.array(values, dtype=float)
            result[f"{key}_mean"] = float(np.mean(arr))
            result[f"{key}_std"] = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        else:
            result[f"{key}_mean"] = 0.0
            result[f"{key}_std"] = 0.0

    return result


def compute_resource_summary(resource_samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary statistics from resource monitoring samples.

    Args:
        resource_samples: List of dicts with keys like 'cpu_percent',
            'mem_usage_mb', 'blk_read_mb', 'blk_write_mb'.

    Returns:
        Dictionary with summary stats (avg, max, min) for each resource metric.
    """
    if not resource_samples:
        return {
            "avg_cpu_percent": 0.0,
            "max_cpu_percent": 0.0,
            "avg_mem_usage_mb": 0.0,
            "max_mem_usage_mb": 0.0,
            "total_blk_read_mb": 0.0,
            "total_blk_write_mb": 0.0,
            "total_net_rx_mb": 0.0,
            "total_net_tx_mb": 0.0,
        }

    cpu_values = np.array(
        [s.get("cpu_percent", 0.0) for s in resource_samples], dtype=float
    )
    mem_values = np.array(
        [s.get("mem_usage_mb", 0.0) for s in resource_samples], dtype=float
    )
    blk_read = np.array(
        [s.get("blk_read_mb", 0.0) for s in resource_samples], dtype=float
    )
    blk_write = np.array(
        [s.get("blk_write_mb", 0.0) for s in resource_samples], dtype=float
    )
    net_rx = np.array(
        [s.get("net_rx_mb", 0.0) for s in resource_samples], dtype=float
    )
    net_tx = np.array(
        [s.get("net_tx_mb", 0.0) for s in resource_samples], dtype=float
    )

    return {
        "avg_cpu_percent": float(np.mean(cpu_values)),
        "max_cpu_percent": float(np.max(cpu_values)),
        "min_cpu_percent": float(np.min(cpu_values)),
        "avg_mem_usage_mb": float(np.mean(mem_values)),
        "max_mem_usage_mb": float(np.max(mem_values)),
        "min_mem_usage_mb": float(np.min(mem_values)),
        "total_blk_read_mb": float(np.max(blk_read) - np.min(blk_read)),
        "total_blk_write_mb": float(np.max(blk_write) - np.min(blk_write)),
        "total_net_rx_mb": float(np.max(net_rx) - np.min(net_rx)),
        "total_net_tx_mb": float(np.max(net_tx) - np.min(net_tx)),
    }


def combine_metrics(
    ycsb_metrics: dict[str, Any],
    resource_summary: dict[str, Any],
    run_config_info: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Combine YCSB metrics with resource utilization into a single result dict.

    Args:
        ycsb_metrics: Parsed YCSB output metrics.
        resource_summary: Resource utilization summary.
        run_config_info: Optional run configuration metadata.

    Returns:
        Combined dictionary with all metrics.
    """
    combined = {}
    if run_config_info:
        combined.update(run_config_info)
    combined.update(ycsb_metrics)
    combined.update(resource_summary)
    return combined


def format_latency_us(latency_us: float) -> str:
    """Format a latency value in microseconds to a human-readable string.

    Args:
        latency_us: Latency in microseconds.

    Returns:
        Formatted string (e.g., '1.23 ms', '456 us', '1.5 s').
    """
    if latency_us < 0:
        return "N/A"
    if latency_us < 1000:
        return f"{latency_us:.0f} us"
    if latency_us < 1_000_000:
        return f"{latency_us / 1000:.2f} ms"
    return f"{latency_us / 1_000_000:.2f} s"


def format_throughput(ops_per_sec: float) -> str:
    """Format throughput to a human-readable string.

    Args:
        ops_per_sec: Operations per second.

    Returns:
        Formatted string (e.g., '1,234 ops/s', '1.2M ops/s').
    """
    if ops_per_sec < 0:
        return "N/A"
    if ops_per_sec < 1000:
        return f"{ops_per_sec:.1f} ops/s"
    if ops_per_sec < 1_000_000:
        return f"{ops_per_sec:,.0f} ops/s"
    return f"{ops_per_sec / 1_000_000:.2f}M ops/s"
