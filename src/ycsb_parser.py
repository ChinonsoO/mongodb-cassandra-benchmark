"""YCSB output parser.

Parses the line-delimited output from YCSB benchmark runs into
structured Python dictionaries for analysis.
"""

from typing import Optional


# YCSB output format: [SECTION], MetricName, Value
# Example: [READ], AverageLatency(us), 38.24


def parse_ycsb_output(raw_output: str) -> dict[str, object]:
    """Parse YCSB stdout output into a structured metrics dictionary.

    YCSB outputs lines in the format:
        [SECTION], MetricName, Value

    This function parses all lines and returns a flat dictionary with
    keys formatted as 'section_metric' (lowercase, spaces replaced).

    Args:
        raw_output: Raw YCSB stdout text.

    Returns:
        Dictionary with parsed metrics. Numeric values are floats,
        string values (like 'Return=OK') are kept as strings.
        Returns empty dict for empty/None input.
    """
    if not raw_output or not raw_output.strip():
        return {}

    results = {}
    for line in raw_output.strip().split("\n"):
        parsed = _parse_line(line)
        if parsed is not None:
            key, value = parsed
            results[key] = value

    return results


def _parse_line(line: str) -> Optional[tuple[str, object]]:
    """Parse a single YCSB output line.

    Args:
        line: A single line from YCSB output.

    Returns:
        Tuple of (key, value) if the line is valid, None otherwise.
    """
    line = line.strip()
    if not line or not line.startswith("["):
        return None

    parts = line.split(",", 2)
    if len(parts) != 3:
        return None

    section = parts[0].strip().strip("[]")
    metric = parts[1].strip()
    value_str = parts[2].strip()

    key = _make_key(section, metric)

    try:
        value = float(value_str)
    except (ValueError, TypeError):
        value = value_str

    return key, value


def _make_key(section: str, metric: str) -> str:
    """Create a normalized dictionary key from section and metric name.

    Args:
        section: YCSB section name (e.g., 'READ', 'OVERALL').
        metric: Metric name (e.g., 'AverageLatency(us)').

    Returns:
        Normalized key string (e.g., 'read_averagelatency_us').
    """
    key = f"{section}_{metric}"
    key = key.lower()
    key = key.replace("(", "_").replace(")", "").replace("/", "_per_")
    key = key.replace(" ", "_")
    # Clean up consecutive underscores
    while "__" in key:
        key = key.replace("__", "_")
    return key.strip("_")


def extract_summary(parsed: dict[str, object]) -> dict[str, object]:
    """Extract the most commonly used metrics from parsed YCSB output.

    Args:
        parsed: Dictionary from parse_ycsb_output().

    Returns:
        Dictionary with standardized summary metric names.
    """
    summary = {}

    # Overall metrics
    summary["throughput_ops_sec"] = parsed.get("overall_throughput_ops_per_sec", 0.0)
    summary["runtime_ms"] = parsed.get("overall_runtime_ms", 0.0)

    # Read metrics
    summary["read_ops"] = parsed.get("read_operations", 0.0)
    summary["read_avg_latency_us"] = parsed.get("read_averagelatency_us", 0.0)
    summary["read_min_latency_us"] = parsed.get("read_minlatency_us", 0.0)
    summary["read_max_latency_us"] = parsed.get("read_maxlatency_us", 0.0)
    summary["read_p95_latency_us"] = parsed.get("read_95thpercentilelatency_us", 0.0)
    summary["read_p99_latency_us"] = parsed.get("read_99thpercentilelatency_us", 0.0)

    # Update metrics
    summary["update_ops"] = parsed.get("update_operations", 0.0)
    summary["update_avg_latency_us"] = parsed.get("update_averagelatency_us", 0.0)
    summary["update_min_latency_us"] = parsed.get("update_minlatency_us", 0.0)
    summary["update_max_latency_us"] = parsed.get("update_maxlatency_us", 0.0)
    summary["update_p95_latency_us"] = parsed.get("update_95thpercentilelatency_us", 0.0)
    summary["update_p99_latency_us"] = parsed.get("update_99thpercentilelatency_us", 0.0)

    # Insert metrics
    summary["insert_ops"] = parsed.get("insert_operations", 0.0)
    summary["insert_avg_latency_us"] = parsed.get("insert_averagelatency_us", 0.0)
    summary["insert_p95_latency_us"] = parsed.get("insert_95thpercentilelatency_us", 0.0)
    summary["insert_p99_latency_us"] = parsed.get("insert_99thpercentilelatency_us", 0.0)

    # Read-Modify-Write metrics
    summary["rmw_ops"] = parsed.get("read-modify-write_operations", 0.0)
    summary["rmw_avg_latency_us"] = parsed.get("read-modify-write_averagelatency_us", 0.0)
    summary["rmw_p95_latency_us"] = parsed.get(
        "read-modify-write_95thpercentilelatency_us", 0.0
    )
    summary["rmw_p99_latency_us"] = parsed.get(
        "read-modify-write_99thpercentilelatency_us", 0.0
    )

    # Status counts
    summary["read_ok"] = parsed.get("read_return=ok", 0.0)
    summary["update_ok"] = parsed.get("update_return=ok", 0.0)
    summary["insert_ok"] = parsed.get("insert_return=ok", 0.0)

    return summary
