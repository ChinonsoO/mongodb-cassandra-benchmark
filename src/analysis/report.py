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
        "Read Avg\n(us)",
        "Read P95\n(us)",
        "Read P99\n(us)",
        "Avg CPU\n(%)",
        "Peak Mem\n(MB)",
    ]

    rows = []
    for r in results:
        rows.append([
            r.get("database", ""),
            r.get("workload_label", r.get("workload", "")),
            r.get("threads", ""),
            r.get("dataset_label", ""),
            _fmt_num(r.get("throughput_ops_sec_mean", 0)),
            _fmt_num(r.get("read_avg_latency_us_mean", 0)),
            _fmt_num(r.get("read_p95_latency_us_mean", 0)),
            _fmt_num(r.get("read_p99_latency_us_mean", 0)),
            _fmt_num(r.get("avg_cpu_percent_mean", r.get("avg_cpu_percent", 0))),
            _fmt_num(r.get("max_mem_usage_mb_mean", r.get("max_mem_usage_mb", 0))),
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


def generate_report(
    all_results: dict[str, list[dict[str, Any]]],
    output_dir: str,
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
