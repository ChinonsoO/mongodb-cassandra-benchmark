"""Visualization module for benchmark results.

Generates charts comparing MongoDB and Cassandra performance
across different workloads, concurrency levels, and dataset sizes.
"""

import logging
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for file output
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from src.analysis.report import identify_saturation_point, _primary_latency_summary

logger = logging.getLogger(__name__)

# Set consistent style
sns.set_theme(style="whitegrid", palette="muted")
COLORS = {"mongodb": "#4DB33D", "cassandra": "#1287B1"}
FIGSIZE = (10, 6)
DPI = 150


def _counter_to_rate(times: list[float], values: list[float]) -> list[float]:
    """Convert monotonically increasing counter values to per-second rates."""
    if not values:
        return []
    rates = [0.0]
    for i in range(1, len(values)):
        delta_t = max(times[i] - times[i - 1], 1e-9)
        delta_v = max(values[i] - values[i - 1], 0.0)
        rates.append(delta_v / delta_t)
    return rates


def _annotate_saturation(
    ax: Any,
    db_results: list[dict[str, Any]],
    db: str,
    metric_key: str,
    color: str | None,
) -> None:
    """Annotate saturation points on concurrency charts."""
    saturation = identify_saturation_point(db_results)
    markers = (
        ("throughput_saturation_threads", "Throughput plateau"),
        ("latency_saturation_threads", "Latency spike"),
    )
    for key, label in markers:
        threads = saturation.get(key)
        if not threads:
            continue

        metric_values = [r.get(metric_key, 0) for r in db_results]
        y_pos = max(metric_values) if metric_values else 0
        ax.axvline(threads, color=color, linestyle="--", linewidth=1, alpha=0.4)
        ax.text(
            threads,
            y_pos,
            f"{db.capitalize()} {label}\n@ {threads} threads",
            rotation=90,
            va="bottom",
            ha="right",
            fontsize=8,
            color=color,
            alpha=0.8,
        )


def plot_throughput_comparison(
    results: list[dict[str, Any]],
    output_path: str,
    title: str = "Throughput Comparison: MongoDB vs Cassandra",
) -> str:
    """Generate a grouped bar chart comparing throughput per workload.

    Args:
        results: Aggregated results with 'database', 'workload_label',
            'throughput_ops_sec_mean', 'throughput_ops_sec_std'.
        output_path: Path to save the chart image.
        title: Chart title.

    Returns:
        Path to the saved chart file.
    """
    fig, ax = plt.subplots(figsize=FIGSIZE)

    databases = sorted(set(r["database"] for r in results))
    workloads = sorted(set(r.get("workload_label", r.get("workload", "")) for r in results))

    x = np.arange(len(workloads))
    width = 0.35

    for i, db in enumerate(databases):
        db_results = [
            r for r in results if r["database"] == db
        ]
        values = []
        errors = []
        for wl in workloads:
            matching = [r for r in db_results if r.get("workload_label", r.get("workload", "")) == wl]
            if matching:
                values.append(matching[0].get("throughput_ops_sec_mean", 0))
                errors.append(matching[0].get("throughput_ops_sec_std", 0))
            else:
                values.append(0)
                errors.append(0)

        offset = (i - len(databases) / 2 + 0.5) * width
        bars = ax.bar(
            x + offset,
            values,
            width,
            yerr=errors,
            label=db.capitalize(),
            color=COLORS.get(db, None),
            capsize=3,
        )

    ax.set_xlabel("Workload")
    ax.set_ylabel("Throughput (ops/sec)")
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(workloads, rotation=15, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Throughput comparison chart saved to {output_path}")
    return output_path


def plot_latency_comparison(
    results: list[dict[str, Any]],
    output_path: str,
    title: str = "Latency Comparison: MongoDB vs Cassandra",
) -> str:
    """Generate a grouped bar chart showing avg/P95/P99 read latency.

    Args:
        results: Aggregated results with latency metrics.
        output_path: Path to save the chart image.
        title: Chart title.

    Returns:
        Path to the saved chart file.
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 6))
    latency_types = [
        ("avg", "Primary Avg Latency (us)"),
        ("p95", "Primary P95 Latency (us)"),
        ("p99", "Primary P99 Latency (us)"),
    ]

    databases = sorted(set(r["database"] for r in results))
    workloads = sorted(set(r.get("workload_label", r.get("workload", "")) for r in results))
    x = np.arange(len(workloads))
    width = 0.35

    for ax, (metric_name, ylabel) in zip(axes, latency_types):
        for i, db in enumerate(databases):
            db_results = [r for r in results if r["database"] == db]
            values = []
            errors = []
            for wl in workloads:
                matching = [r for r in db_results if r.get("workload_label", r.get("workload", "")) == wl]
                if matching:
                    latency = _primary_latency_summary(matching[0])
                    values.append(latency.get(metric_name, 0))
                    errors.append(
                        matching[0].get(
                            f"{latency['op']}_{metric_name}_latency_us_std",
                            0,
                        )
                    )
                else:
                    values.append(0)
                    errors.append(0)

            offset = (i - len(databases) / 2 + 0.5) * width
            ax.bar(
                x + offset,
                values,
                width,
                yerr=errors,
                label=db.capitalize(),
                color=COLORS.get(db, None),
                capsize=3,
            )

        ax.set_xlabel("Workload")
        ax.set_ylabel(ylabel)
        ax.set_xticks(x)
        ax.set_xticklabels(workloads, rotation=15, ha="right")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)

    fig.suptitle(title, fontsize=14)
    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Latency comparison chart saved to {output_path}")
    return output_path


def plot_throughput_vs_concurrency(
    results: list[dict[str, Any]],
    output_path: str,
    title: str = "Throughput vs Concurrency",
) -> str:
    """Generate a line chart of throughput vs thread count per database.

    Helps identify the saturation point where throughput plateaus.

    Args:
        results: Aggregated results with 'threads' and 'throughput_ops_sec_mean'.
        output_path: Path to save the chart image.
        title: Chart title.

    Returns:
        Path to the saved chart file.
    """
    fig, ax = plt.subplots(figsize=FIGSIZE)

    databases = sorted(set(r["database"] for r in results))

    for db in databases:
        db_results = sorted(
            [r for r in results if r["database"] == db],
            key=lambda r: r.get("threads", 0),
        )
        threads = [r.get("threads", 0) for r in db_results]
        throughput = [r.get("throughput_ops_sec_mean", 0) for r in db_results]
        errors = [r.get("throughput_ops_sec_std", 0) for r in db_results]

        ax.errorbar(
            threads,
            throughput,
            yerr=errors,
            marker="o",
            label=db.capitalize(),
            color=COLORS.get(db, None),
            capsize=3,
            linewidth=2,
        )
        _annotate_saturation(
            ax,
            db_results,
            db,
            "throughput_ops_sec_mean",
            COLORS.get(db, None),
        )

    ax.set_xlabel("Number of Threads")
    ax.set_ylabel("Throughput (ops/sec)")
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Throughput vs concurrency chart saved to {output_path}")
    return output_path


def plot_latency_vs_concurrency(
    results: list[dict[str, Any]],
    output_path: str,
    title: str = "P99 Latency vs Concurrency",
) -> str:
    """Generate a line chart of P99 latency vs thread count per database.

    Args:
        results: Aggregated results with 'threads' and latency metrics.
        output_path: Path to save the chart image.
        title: Chart title.

    Returns:
        Path to the saved chart file.
    """
    fig, ax = plt.subplots(figsize=FIGSIZE)

    databases = sorted(set(r["database"] for r in results))

    for db in databases:
        db_results = sorted(
            [r for r in results if r["database"] == db],
            key=lambda r: r.get("threads", 0),
        )
        threads = [r.get("threads", 0) for r in db_results]
        latency = [r.get("read_p99_latency_us_mean", 0) for r in db_results]
        errors = [r.get("read_p99_latency_us_std", 0) for r in db_results]

        ax.errorbar(
            threads,
            latency,
            yerr=errors,
            marker="s",
            label=db.capitalize(),
            color=COLORS.get(db, None),
            linewidth=2,
            capsize=3,
        )
        _annotate_saturation(
            ax,
            db_results,
            db,
            "read_p99_latency_us_mean",
            COLORS.get(db, None),
        )

    ax.set_xlabel("Number of Threads")
    ax.set_ylabel("P99 Read Latency (us)")
    ax.set_title(title)
    ax.legend()
    ax.grid(alpha=0.3)

    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Latency vs concurrency chart saved to {output_path}")
    return output_path


def plot_resource_utilization(
    resource_data: list[dict[str, Any]],
    output_path: str,
    title: str = "Resource Utilization Over Time",
) -> str:
    """Generate time-series charts of CPU, memory, and disk I/O.

    Args:
        resource_data: List of resource sample dictionaries with timestamps.
        output_path: Path to save the chart image.
        title: Chart title.

    Returns:
        Path to the saved chart file.
    """
    if not resource_data:
        logger.warning("No resource data to plot")
        return output_path

    fig, axes = plt.subplots(4, 1, figsize=(12, 12), sharex=True)

    # Normalize timestamps to start from 0
    t0 = resource_data[0].get("timestamp", 0)
    times = [s.get("timestamp", 0) - t0 for s in resource_data]

    # CPU
    cpu = [s.get("cpu_percent", 0) for s in resource_data]
    axes[0].plot(times, cpu, color="#e74c3c", linewidth=1.5)
    axes[0].set_ylabel("CPU (%)")
    axes[0].set_title("CPU Utilization")
    axes[0].grid(alpha=0.3)

    # Memory
    mem = [s.get("mem_usage_mb", 0) for s in resource_data]
    axes[1].plot(times, mem, color="#3498db", linewidth=1.5)
    axes[1].set_ylabel("Memory (MB)")
    axes[1].set_title("Memory Usage")
    axes[1].grid(alpha=0.3)

    # Disk I/O rate
    blk_read = [s.get("blk_read_mb", 0) for s in resource_data]
    blk_write = [s.get("blk_write_mb", 0) for s in resource_data]
    axes[2].plot(
        times, _counter_to_rate(times, blk_read),
        label="Read", color="#2ecc71", linewidth=1.5,
    )
    axes[2].plot(
        times, _counter_to_rate(times, blk_write),
        label="Write", color="#e67e22", linewidth=1.5,
    )
    axes[2].set_ylabel("Block I/O (MB/s)")
    axes[2].set_xlabel("Time (seconds)")
    axes[2].set_title("Disk I/O Rate")
    axes[2].legend()
    axes[2].grid(alpha=0.3)

    # Network I/O rate
    net_rx = [s.get("net_rx_mb", 0) for s in resource_data]
    net_tx = [s.get("net_tx_mb", 0) for s in resource_data]
    axes[3].plot(
        times, _counter_to_rate(times, net_rx),
        label="RX", color="#8e44ad", linewidth=1.5,
    )
    axes[3].plot(
        times, _counter_to_rate(times, net_tx),
        label="TX", color="#16a085", linewidth=1.5,
    )
    axes[3].set_ylabel("Network (MB/s)")
    axes[3].set_xlabel("Time (seconds)")
    axes[3].set_title("Network I/O Rate")
    axes[3].legend()
    axes[3].grid(alpha=0.3)

    fig.suptitle(title, fontsize=14)
    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Resource utilization chart saved to {output_path}")
    return output_path


def plot_dataset_scaling(
    results: list[dict[str, Any]],
    output_path: str,
    title: str = "Performance vs Dataset Size",
) -> str:
    """Generate charts showing throughput and latency vs dataset size.

    Args:
        results: Aggregated results with 'record_count' field.
        output_path: Path to save the chart image.
        title: Chart title.

    Returns:
        Path to the saved chart file.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    databases = sorted(set(r["database"] for r in results))

    for db in databases:
        db_results = sorted(
            [r for r in results if r["database"] == db],
            key=lambda r: r.get("record_count", 0),
        )
        records = [r.get("record_count", 0) for r in db_results]
        labels = [r.get("dataset_label", str(r.get("record_count", ""))) for r in db_results]
        throughput = [r.get("throughput_ops_sec_mean", 0) for r in db_results]
        throughput_std = [r.get("throughput_ops_sec_std", 0) for r in db_results]
        p99_latency = [r.get("read_p99_latency_us_mean", 0) for r in db_results]
        p99_latency_std = [r.get("read_p99_latency_us_std", 0) for r in db_results]

        ax1.errorbar(
            range(len(records)), throughput,
            yerr=throughput_std,
            marker="o", label=db.capitalize(),
            color=COLORS.get(db, None), linewidth=2, capsize=3,
        )
        ax2.errorbar(
            range(len(records)), p99_latency,
            yerr=p99_latency_std,
            marker="s", label=db.capitalize(),
            color=COLORS.get(db, None), linewidth=2, capsize=3,
        )

    ax1.set_xlabel("Dataset Size")
    ax1.set_ylabel("Throughput (ops/sec)")
    ax1.set_title("Throughput vs Dataset Size")
    ax1.legend()
    ax1.grid(alpha=0.3)

    ax2.set_xlabel("Dataset Size")
    ax2.set_ylabel("P99 Read Latency (us)")
    ax2.set_title("P99 Latency vs Dataset Size")
    ax2.legend()
    ax2.grid(alpha=0.3)

    # Set x-tick labels (use labels from last db)
    if databases and db_results:
        for ax in (ax1, ax2):
            ax.set_xticks(range(len(records)))
            ax.set_xticklabels(labels)

    fig.suptitle(title, fontsize=14)
    plt.tight_layout()
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Dataset scaling chart saved to {output_path}")
    return output_path


def generate_resource_charts(
    raw_results: dict[str, list[dict[str, Any]]],
    output_dir: str,
) -> list[str]:
    """Generate per-run resource charts from raw benchmark results."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for series_results in raw_results.values():
        for result in series_results:
            run_id = result.get("run_id")
            resource_samples = result.get("resource_samples", [])
            if not run_id or not resource_samples:
                continue

            path = str(output_dir / f"resource_{run_id}.png")
            title = (
                f"Resource Utilization: {result.get('database', '').capitalize()} "
                f"{result.get('workload_label', result.get('workload', ''))} "
                f"(Run {result.get('repetition', '?')})"
            )
            plot_resource_utilization(resource_samples, path, title=title)
            generated.append(path)

    return generated


def generate_all_charts(
    all_results: dict[str, list[dict[str, Any]]],
    output_dir: str,
    raw_results: dict[str, list[dict[str, Any]]] | None = None,
) -> list[str]:
    """Generate all charts for a complete experiment.

    Args:
        all_results: Dictionary mapping series names to aggregated results.
        output_dir: Directory to save chart images.

    Returns:
        List of paths to generated chart files.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    if "workload" in all_results and all_results["workload"]:
        path = str(output_dir / "throughput_comparison.png")
        plot_throughput_comparison(all_results["workload"], path)
        generated.append(path)

        path = str(output_dir / "latency_comparison.png")
        plot_latency_comparison(all_results["workload"], path)
        generated.append(path)

    if "concurrency" in all_results and all_results["concurrency"]:
        path = str(output_dir / "throughput_vs_concurrency.png")
        plot_throughput_vs_concurrency(all_results["concurrency"], path)
        generated.append(path)

        path = str(output_dir / "latency_vs_concurrency.png")
        plot_latency_vs_concurrency(all_results["concurrency"], path)
        generated.append(path)

    if "stress" in all_results and all_results["stress"]:
        path = str(output_dir / "stress_throughput.png")
        plot_throughput_vs_concurrency(
            all_results["stress"], path, title="Stress Test: Throughput vs Concurrency"
        )
        generated.append(path)

        path = str(output_dir / "stress_latency.png")
        plot_latency_vs_concurrency(
            all_results["stress"], path, title="Stress Test: P99 Latency vs Concurrency"
        )
        generated.append(path)

    if "dataset_size" in all_results and all_results["dataset_size"]:
        path = str(output_dir / "dataset_scaling.png")
        plot_dataset_scaling(all_results["dataset_size"], path)
        generated.append(path)

    if raw_results:
        generated.extend(generate_resource_charts(raw_results, str(output_dir)))

    logger.info(f"Generated {len(generated)} charts in {output_dir}")
    return generated
