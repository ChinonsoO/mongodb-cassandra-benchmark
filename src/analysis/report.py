"""Report generation for benchmark results.

Produces summary tables (terminal + file) and CSV exports.
"""

import csv
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from tabulate import tabulate

logger = logging.getLogger(__name__)


PRIMARY_OPERATION_HINTS = (
    ("insert", ("bulk", "insert")),
    ("rmw", ("read-modify-write", "workload_f", "rmw")),
    ("update", ("update", "workload_a", "stress")),
    ("read", ("read", "workload_b")),
)


def _metric_value(row: dict[str, Any], key: str) -> float:
    """Read a metric from aggregated or raw result rows."""
    return float(row.get(f"{key}_mean", row.get(key, 0)) or 0)


def _select_primary_operation(row: dict[str, Any]) -> str:
    """Choose the most representative operation for summary reporting."""
    text = " ".join([
        str(row.get("workload_label", "")),
        str(row.get("workload", "")),
    ]).lower()

    for op, hints in PRIMARY_OPERATION_HINTS:
        if any(hint in text for hint in hints):
            if any(
                _metric_value(row, f"{op}_{metric}") > 0
                for metric in ("ops", "avg_latency_us", "p95_latency_us", "p99_latency_us")
            ):
                return op

    ordered_ops = ("update", "read", "rmw", "insert")
    best_op = "read"
    best_score = (-1.0, -1.0, float("-inf"))
    for priority, op in enumerate(ordered_ops):
        score = (
            _metric_value(row, f"{op}_ops"),
            1.0 if any(
                _metric_value(row, f"{op}_{metric}") > 0
                for metric in ("avg_latency_us", "p95_latency_us", "p99_latency_us")
            ) else 0.0,
            -priority,
        )
        if score > best_score:
            best_op = op
            best_score = score
    return best_op


def _primary_latency_summary(row: dict[str, Any]) -> dict[str, Any]:
    """Return the primary operation label and latency metrics for a result row."""
    labels = {
        "read": "Read",
        "update": "Update",
        "insert": "Insert",
        "rmw": "RMW",
    }
    op = _select_primary_operation(row)
    summary = {
        "op": op,
        "label": labels[op],
        "avg": _metric_value(row, f"{op}_avg_latency_us"),
        "p95": _metric_value(row, f"{op}_p95_latency_us"),
        "p99": _metric_value(row, f"{op}_p99_latency_us"),
    }

    if summary["avg"] == 0 and summary["p95"] == 0 and summary["p99"] == 0 and op != "read":
        return {
            "op": "read",
            "label": labels["read"],
            "avg": _metric_value(row, "read_avg_latency_us"),
            "p95": _metric_value(row, "read_p95_latency_us"),
            "p99": _metric_value(row, "read_p99_latency_us"),
        }
    return summary


def generate_summary_table(
    results: list[dict[str, Any]],
    title: str = "Benchmark Summary",
) -> str:
    """Generate a formatted summary table from aggregated results.

    Args:
        results: List of aggregated result dictionaries.
        title: Title to display above the table.

    Returns:
        Formatted table string suitable for terminal output.
    """
    if not results:
        return f"{title}\n(No results to display)"

    # Build table rows
    headers = [
        "Database",
        "Workload",
        "Threads",
        "Dataset",
        "Throughput\n(ops/sec)",
        "Latency\nFocus",
        "Avg\n(us)",
        "P95\n(us)",
        "P99\n(us)",
        "Avg CPU\n(%)",
        "Peak Mem\n(MB)",
    ]

    rows = []
    for r in results:
        latency = _primary_latency_summary(r)
        rows.append([
            r.get("database", ""),
            r.get("workload_label", r.get("workload", "")),
            r.get("threads", ""),
            r.get("dataset_label", ""),
            _fmt_num(_metric_value(r, "throughput_ops_sec")),
            latency["label"],
            _fmt_num(latency["avg"]),
            _fmt_num(latency["p95"]),
            _fmt_num(latency["p99"]),
            _fmt_num(_metric_value(r, "avg_cpu_percent")),
            _fmt_num(_metric_value(r, "max_mem_usage_mb")),
        ])

    table = tabulate(rows, headers=headers, tablefmt="grid", floatfmt=".2f")
    return f"\n{title}\n{'=' * len(title)}\n{table}\n"


def generate_csv(
    results: list[dict[str, Any]],
    output_path: str,
) -> str:
    """Export results to a CSV file.

    Args:
        results: List of result dictionaries.
        output_path: Path to write the CSV file.

    Returns:
        Path to the generated CSV file.
    """
    if not results:
        logger.warning("No results to export to CSV")
        return output_path

    # Use pandas for clean CSV export
    df = pd.DataFrame(results)

    # Select and order important columns
    priority_cols = [
        "database", "workload", "workload_label", "threads",
        "record_count", "dataset_label", "series",
    ]
    metric_cols = [
        "throughput_ops_sec_mean", "throughput_ops_sec_std",
        "read_avg_latency_us_mean", "read_p95_latency_us_mean",
        "read_p99_latency_us_mean",
        "update_avg_latency_us_mean", "update_p95_latency_us_mean",
        "update_p99_latency_us_mean",
        "avg_cpu_percent_mean", "max_cpu_percent_mean",
        "avg_mem_usage_mb_mean", "max_mem_usage_mb_mean",
        "total_blk_read_mb_mean", "total_blk_write_mb_mean",
    ]

    # Use columns that exist in the DataFrame
    columns = [c for c in priority_cols + metric_cols if c in df.columns]
    remaining = [c for c in df.columns if c not in columns]
    df = df[columns + remaining]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    logger.info(f"Results exported to {output_path}")
    return str(output_path)


def identify_saturation_point(
    results: list[dict[str, Any]],
    throughput_threshold: float = 0.05,
    latency_multiplier: float = 2.0,
) -> dict[str, Any]:
    """Identify the concurrency saturation point.

    The saturation point is where throughput plateaus (< threshold increase)
    and/or latency spikes (> multiplier of baseline).

    Args:
        results: Aggregated results sorted by thread count.
        throughput_threshold: Minimum relative throughput increase to consider
            non-saturated (default 5%).
        latency_multiplier: Factor above baseline P99 latency that indicates
            saturation (default 2x).

    Returns:
        Dictionary with saturation analysis including:
        - 'throughput_saturation_threads': thread count where throughput plateaus
        - 'latency_saturation_threads': thread count where latency spikes
        - 'details': per-thread-level metrics
    """
    if not results or len(results) < 2:
        return {
            "throughput_saturation_threads": None,
            "latency_saturation_threads": None,
            "details": [],
        }

    # Sort by thread count
    sorted_results = sorted(results, key=lambda r: r.get("threads", 0))

    # Analyze throughput plateau
    throughput_sat_threads = None
    baseline_latency = sorted_results[0].get("read_p99_latency_us_mean", 0)
    latency_sat_threads = None

    details = []
    prev_throughput = 0

    for i, r in enumerate(sorted_results):
        threads = r.get("threads", 0)
        throughput = r.get("throughput_ops_sec_mean", 0)
        p99_latency = r.get("read_p99_latency_us_mean", 0)

        relative_increase = 0
        if prev_throughput > 0:
            relative_increase = (throughput - prev_throughput) / prev_throughput

        # Check throughput saturation
        if (
            i > 0
            and throughput_sat_threads is None
            and relative_increase < throughput_threshold
        ):
            throughput_sat_threads = threads

        # Check latency saturation
        if (
            baseline_latency > 0
            and latency_sat_threads is None
            and p99_latency > baseline_latency * latency_multiplier
        ):
            latency_sat_threads = threads

        details.append({
            "threads": threads,
            "throughput_ops_sec": throughput,
            "p99_latency_us": p99_latency,
            "relative_throughput_increase": relative_increase,
        })

        prev_throughput = throughput

    return {
        "throughput_saturation_threads": throughput_sat_threads,
        "latency_saturation_threads": latency_sat_threads,
        "details": details,
    }


def _find_environment_snapshot(
    raw_results: dict[str, list[dict[str, Any]]] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Extract a representative environment snapshot plus container entries."""
    if not raw_results:
        return {}, []

    first_environment: dict[str, Any] = {}
    containers: dict[str, dict[str, Any]] = {}

    for series_results in raw_results.values():
        for result in series_results:
            environment = result.get("environment", {})
            if not isinstance(environment, dict):
                continue

            if not first_environment:
                first_environment = environment

            container = environment.get("target_container", {})
            if not isinstance(container, dict):
                continue
            name = container.get("name")
            if name and name not in containers:
                containers[name] = container

    return first_environment, list(containers.values())


def _build_environment_summary(
    raw_results: dict[str, list[dict[str, Any]]] | None,
) -> list[str]:
    """Build a text summary of the benchmark execution environment."""
    environment, containers = _find_environment_snapshot(raw_results)
    if not environment:
        return []

    lines = ["", "Environment Summary:"]

    host = environment.get("host", {})
    if isinstance(host, dict):
        host_bits = [
            host.get("hostname"),
            host.get("platform"),
            host.get("platform_release"),
            host.get("machine"),
        ]
        host_bits = [str(v) for v in host_bits if v]
        if host.get("logical_cpus") is not None:
            host_bits.append(f"{host['logical_cpus']} logical CPUs")
        if host_bits:
            lines.append(f"  Host: {', '.join(host_bits)}")

    runtime = environment.get("runtime", {})
    if isinstance(runtime, dict):
        runtime_bits = []
        if runtime.get("python_version"):
            runtime_bits.append(f"Python {runtime['python_version']}")
        if runtime.get("java_version"):
            runtime_bits.append(runtime["java_version"])
        elif runtime.get("java_executable"):
            runtime_bits.append(f"Java via {runtime['java_executable']}")
        if runtime.get("ycsb_path"):
            runtime_bits.append(f"YCSB {runtime['ycsb_path']}")
        if runtime_bits:
            lines.append(f"  Runtime: {', '.join(str(v) for v in runtime_bits)}")

    docker = environment.get("docker", {})
    if isinstance(docker, dict) and docker:
        docker_bits = []
        if docker.get("server_version"):
            docker_bits.append(f"Docker {docker['server_version']}")
        if docker.get("operating_system"):
            docker_bits.append(str(docker["operating_system"]))
        if docker.get("engine_cpus") is not None:
            docker_bits.append(f"{docker['engine_cpus']} engine CPUs")
        if docker.get("engine_memory_mb") is not None:
            docker_bits.append(f"{docker['engine_memory_mb']:.0f} MB engine memory")
        if docker_bits:
            lines.append(f"  Docker: {', '.join(docker_bits)}")

    if containers:
        for container in containers:
            container_bits = []
            if container.get("image"):
                container_bits.append(str(container["image"]))
            if container.get("cpus") is not None:
                container_bits.append(f"{container['cpus']} CPU quota")
            if container.get("cpuset_cpus"):
                container_bits.append(f"cpuset {container['cpuset_cpus']}")
            if container.get("memory_limit_mb") is not None:
                container_bits.append(f"{container['memory_limit_mb']:.0f} MB memory")
            label = container.get("name", "container")
            lines.append(f"  Container {label}: {', '.join(container_bits)}")

    return lines


def generate_report(
    all_results: dict[str, list[dict[str, Any]]],
    output_dir: str,
    raw_results: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    """Generate a complete benchmark report with tables and CSV exports.

    Args:
        all_results: Dictionary mapping series names to aggregated results.
        output_dir: Directory to save report files.

    Returns:
        Summary text suitable for terminal output.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report_lines = ["\n" + "=" * 60]
    report_lines.append("  BENCHMARK RESULTS SUMMARY")
    report_lines.append("=" * 60)
    report_lines.extend(_build_environment_summary(raw_results))

    # Generate table for each series
    for series_name, results in all_results.items():
        if not results:
            continue

        table = generate_summary_table(
            results,
            title=f"Series: {series_name.replace('_', ' ').title()}",
        )
        report_lines.append(table)

        # Export CSV for this series
        csv_path = str(output_dir / f"{series_name}_results.csv")
        generate_csv(results, csv_path)

    # Saturation analysis for concurrency/stress series
    for series_name in ("concurrency", "stress"):
        if series_name in all_results and all_results[series_name]:
            databases = set(r.get("database") for r in all_results[series_name])
            for db in databases:
                db_results = [
                    r for r in all_results[series_name]
                    if r.get("database") == db
                ]
                sat = identify_saturation_point(db_results)
                report_lines.append(
                    f"\nSaturation Analysis ({db.capitalize()} - {series_name}):"
                )
                report_lines.append(
                    f"  Throughput plateau at: {sat['throughput_saturation_threads'] or 'N/A'} threads"
                )
                report_lines.append(
                    f"  Latency spike at: {sat['latency_saturation_threads'] or 'N/A'} threads"
                )

    # Export combined CSV
    all_flat = []
    for series_name, results in all_results.items():
        for r in results:
            r_copy = dict(r)
            r_copy["series"] = series_name
            all_flat.append(r_copy)

    if all_flat:
        combined_csv = str(output_dir / "all_results.csv")
        generate_csv(all_flat, combined_csv)
        report_lines.append(f"\nFull results exported to: {combined_csv}")

    report_lines.append("\n" + "=" * 60)

    full_report = "\n".join(report_lines)

    # Save report text
    report_path = output_dir / "summary_report.txt"
    with open(report_path, "w") as f:
        f.write(full_report)
    logger.info(f"Report saved to {report_path}")

    return full_report


def _fmt_num(value: Any) -> str:
    """Format a numeric value for table display."""
    if value is None or value == "":
        return "N/A"
    try:
        v = float(value)
        if v == 0:
            return "0"
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        if abs(v) >= 1:
            return f"{v:.2f}"
        return f"{v:.4f}"
    except (ValueError, TypeError):
        return str(value)
