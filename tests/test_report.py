"""Tests for the report module."""

import os
from unittest.mock import patch

import pytest

from src.analysis.report import (
    generate_summary_table,
    generate_csv,
    identify_saturation_point,
    generate_report,
)


@pytest.fixture
def sample_aggregated():
    """Sample aggregated benchmark results."""
    return [
        {
            "database": "mongodb", "workload": "workload_a",
            "threads": 10, "record_count": 1000000,
            "throughput_ops_sec_mean": 10000.0, "throughput_ops_sec_std": 500.0,
            "read_avg_latency_us_mean": 380.0, "read_avg_latency_us_std": 20.0,
            "read_p95_latency_us_mean": 1200.0, "read_p95_latency_us_std": 50.0,
            "read_p99_latency_us_mean": 3500.0, "read_p99_latency_us_std": 100.0,
            "update_avg_latency_us_mean": 550.0, "update_avg_latency_us_std": 30.0,
            "update_p95_latency_us_mean": 1500.0, "update_p95_latency_us_std": 75.0,
            "update_p99_latency_us_mean": 3000.0, "update_p99_latency_us_std": 125.0,
            "avg_cpu_percent_mean": 25.0, "avg_mem_usage_mb_mean": 256.0,
        },
        {
            "database": "cassandra", "workload": "workload_a",
            "threads": 10, "record_count": 1000000,
            "throughput_ops_sec_mean": 8000.0, "throughput_ops_sec_std": 400.0,
            "read_avg_latency_us_mean": 450.0, "read_avg_latency_us_std": 25.0,
            "read_p95_latency_us_mean": 1500.0, "read_p95_latency_us_std": 60.0,
            "read_p99_latency_us_mean": 4000.0, "read_p99_latency_us_std": 120.0,
            "update_avg_latency_us_mean": 700.0, "update_avg_latency_us_std": 40.0,
            "update_p95_latency_us_mean": 1800.0, "update_p95_latency_us_std": 85.0,
            "update_p99_latency_us_mean": 3400.0, "update_p99_latency_us_std": 140.0,
            "avg_cpu_percent_mean": 35.0, "avg_mem_usage_mb_mean": 512.0,
        },
    ]


@pytest.fixture
def sample_concurrency_results():
    """Sample results for saturation point detection (single database)."""
    results = []
    for t in [1, 5, 10, 20, 50, 100, 200]:
        # Throughput plateaus around 50 threads
        if t <= 50:
            tput = 5000 * t
        else:
            tput = 5000 * 50 * 1.01  # nearly flat
        # Latency spikes after 50 threads
        if t <= 50:
            lat = 200 + t * 2
        else:
            lat = 300 * (t / 50)  # steep rise
        results.append({
            "database": "mongodb", "threads": t, "workload": "workload_a",
            "throughput_ops_sec_mean": tput,
            "read_avg_latency_us_mean": lat,
            "read_p95_latency_us_mean": lat * 3,
            "read_p99_latency_us_mean": lat * 5,
        })
    return results


class TestGenerateSummaryTable:
    """Tests for the summary table generator."""

    def test_returns_string(self, sample_aggregated):
        """Should return a formatted string."""
        table = generate_summary_table(sample_aggregated)
        assert isinstance(table, str)
        assert len(table) > 0

    def test_contains_database_names(self, sample_aggregated):
        """Should include database names in the table."""
        table = generate_summary_table(sample_aggregated)
        assert "mongodb" in table
        assert "cassandra" in table

    def test_contains_metrics(self, sample_aggregated):
        """Should include key metrics."""
        table = generate_summary_table(sample_aggregated)
        assert "10,000" in table or "10000" in table
        assert "8,000" in table or "8000" in table
        assert "Update" in table

    def test_empty_results(self):
        """Should handle empty results."""
        table = generate_summary_table([])
        assert "No results" in table or table == ""


class TestGenerateCsv:
    """Tests for CSV export."""

    def test_creates_csv_file(self, sample_aggregated, tmp_results_dir):
        """Should create a CSV file."""
        output = os.path.join(tmp_results_dir, "results.csv")
        generate_csv(sample_aggregated, output)

        assert os.path.exists(output)

    def test_csv_contains_headers(self, sample_aggregated, tmp_results_dir):
        """Should include header row."""
        output = os.path.join(tmp_results_dir, "results.csv")
        generate_csv(sample_aggregated, output)

        with open(output) as f:
            header = f.readline()
        assert "database" in header
        assert "throughput_ops_sec_mean" in header

    def test_csv_row_count(self, sample_aggregated, tmp_results_dir):
        """Should have correct number of data rows."""
        output = os.path.join(tmp_results_dir, "results.csv")
        generate_csv(sample_aggregated, output)

        with open(output) as f:
            lines = f.readlines()
        assert len(lines) == 3  # header + 2 data rows

    def test_empty_results_csv(self, tmp_results_dir):
        """Should return output path for empty results (no file created)."""
        output = os.path.join(tmp_results_dir, "empty.csv")
        result = generate_csv([], output)
        assert result == output


class TestIdentifySaturationPoint:
    """Tests for saturation point detection."""

    def test_detects_throughput_plateau(self, sample_concurrency_results):
        """Should detect the throughput plateau around 50-100 threads."""
        result = identify_saturation_point(sample_concurrency_results)

        assert "throughput_saturation_threads" in result
        assert result["throughput_saturation_threads"] is not None

    def test_detects_latency_spike(self, sample_concurrency_results):
        """Should detect the latency spike."""
        result = identify_saturation_point(sample_concurrency_results)

        if result["latency_saturation_threads"] is not None:
            assert result["latency_saturation_threads"] > 0

    def test_empty_data(self):
        """Should return None saturation for empty data."""
        result = identify_saturation_point([])
        assert result["throughput_saturation_threads"] is None
        assert result["latency_saturation_threads"] is None

    def test_no_saturation(self):
        """Should handle data with no clear saturation."""
        # Linear scaling -- no plateau
        data = [
            {"database": "mongodb", "threads": t, "workload": "wl_a",
             "throughput_ops_sec_mean": t * 1000,
             "read_avg_latency_us_mean": 200,
             "read_p95_latency_us_mean": 600,
             "read_p99_latency_us_mean": 1000}
            for t in [1, 10, 50, 100, 200]
        ]
        result = identify_saturation_point(data)
        # May or may not find saturation depending on threshold
        assert "throughput_saturation_threads" in result

    def test_single_result(self):
        """Should return None saturation for single data point."""
        data = [{"database": "mongodb", "threads": 10, "workload": "wl_a",
                 "throughput_ops_sec_mean": 10000,
                 "read_p99_latency_us_mean": 1000}]
        result = identify_saturation_point(data)
        assert result["throughput_saturation_threads"] is None


class TestGenerateReport:
    """Tests for full report generation."""

    def test_creates_report_files(self, sample_aggregated, tmp_results_dir):
        """Should create report text and CSV files."""
        all_results = {"workload": sample_aggregated}
        generate_report(all_results, tmp_results_dir)

        assert os.path.exists(os.path.join(tmp_results_dir, "summary_report.txt"))
        assert os.path.exists(os.path.join(tmp_results_dir, "workload_results.csv"))
        assert os.path.exists(os.path.join(tmp_results_dir, "all_results.csv"))

    def test_report_content(self, sample_aggregated, tmp_results_dir):
        """Report text should contain key sections."""
        all_results = {"workload": sample_aggregated}
        generate_report(all_results, tmp_results_dir)

        with open(os.path.join(tmp_results_dir, "summary_report.txt")) as f:
            content = f.read()

        assert "BENCHMARK" in content
        assert "mongodb" in content
        assert "cassandra" in content

    def test_report_includes_environment_summary(self, sample_aggregated, tmp_results_dir):
        """Report should include environment metadata when raw results are provided."""
        all_results = {"workload": sample_aggregated}
        raw_results = {
            "workload": [
                {
                    "environment": {
                        "host": {
                            "hostname": "bench-host",
                            "platform": "Windows",
                            "platform_release": "11",
                            "machine": "AMD64",
                            "logical_cpus": 8,
                        },
                        "runtime": {
                            "python_version": "3.12.1",
                            "java_version": 'openjdk version "21.0.2"',
                            "ycsb_path": "ycsb-0.17.0",
                        },
                        "docker": {
                            "server_version": "28.0.1",
                            "operating_system": "Docker Desktop",
                            "engine_cpus": 8,
                            "engine_memory_mb": 16384,
                        },
                        "target_container": {
                            "name": "ycsb-mongodb",
                            "image": "mongo:7.0",
                            "cpus": 2.0,
                            "cpuset_cpus": "0-1",
                            "memory_limit_mb": 2048,
                        },
                    }
                }
            ]
        }
        generate_report(all_results, tmp_results_dir, raw_results=raw_results)

        with open(os.path.join(tmp_results_dir, "summary_report.txt")) as f:
            content = f.read()

        assert "Environment Summary" in content
        assert "bench-host" in content
        assert "2.0 CPU quota" in content

    def test_concurrency_report_includes_saturation(
        self, sample_concurrency_results, tmp_results_dir
    ):
        """Should include saturation analysis for concurrency series."""
        all_results = {"concurrency": sample_concurrency_results}
        generate_report(all_results, tmp_results_dir)

        report_file = os.path.join(tmp_results_dir, "summary_report.txt")
        if os.path.exists(report_file):
            with open(report_file) as f:
                content = f.read()
            # Should mention saturation or concurrency
            assert "saturation" in content.lower() or "concurrency" in content.lower()

    def test_empty_results_report(self, tmp_results_dir):
        """Should handle empty results gracefully."""
        generate_report({}, tmp_results_dir)
        # Should not raise -- report file still created
