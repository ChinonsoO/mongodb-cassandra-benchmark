"""Tests for the metrics module."""

import pytest
import numpy as np

from src.metrics import (
    aggregate_runs,
    compute_resource_summary,
    combine_metrics,
    format_latency_us,
    format_throughput,
)


class TestAggregateRuns:
    """Tests for the aggregate_runs function."""

    def test_single_run(self):
        """Single run should return values with zero std."""
        results = [{"throughput": 1000.0, "latency": 500.0}]
        agg = aggregate_runs(results)

        assert agg["throughput_mean"] == 1000.0
        assert agg["throughput_std"] == 0.0
        assert agg["latency_mean"] == 500.0
        assert agg["latency_std"] == 0.0

    def test_multiple_runs(self):
        """Multiple runs should compute correct mean and std."""
        results = [
            {"throughput": 1000.0, "latency": 500.0},
            {"throughput": 1200.0, "latency": 600.0},
            {"throughput": 1100.0, "latency": 550.0},
        ]
        agg = aggregate_runs(results)

        expected_mean = np.mean([1000.0, 1200.0, 1100.0])
        expected_std = np.std([1000.0, 1200.0, 1100.0], ddof=1)
        assert abs(agg["throughput_mean"] - expected_mean) < 0.01
        assert abs(agg["throughput_std"] - expected_std) < 0.01

    def test_preserves_non_numeric(self):
        """Non-numeric values should be passed through."""
        results = [
            {"throughput": 1000.0, "status": "success"},
            {"throughput": 1200.0, "status": "success"},
        ]
        agg = aggregate_runs(results)
        assert agg["status"] == "success"

    def test_empty_raises(self):
        """Empty list should raise ValueError."""
        with pytest.raises(ValueError, match="Cannot aggregate empty"):
            aggregate_runs([])

    def test_all_zeros(self):
        """Should handle all-zero values correctly."""
        results = [
            {"throughput": 0.0, "latency": 0.0},
            {"throughput": 0.0, "latency": 0.0},
        ]
        agg = aggregate_runs(results)
        assert agg["throughput_mean"] == 0.0
        assert agg["throughput_std"] == 0.0

    def test_integer_values(self):
        """Should handle integer values."""
        results = [
            {"ops": 100, "time_ms": 5000},
            {"ops": 120, "time_ms": 5500},
        ]
        agg = aggregate_runs(results)
        assert abs(agg["ops_mean"] - 110.0) < 0.01
    
    def test_mixed_numeric_types(self):
        """Mix of ints and floats should work correctly."""
        results = [
            {"throughput": 1000, "latency": 500.0},
            {"throughput": 1200.5, "latency": 600},
        ]
        agg = aggregate_runs(results)
        assert abs(agg["throughput_mean"] - 1100.25) < 0.01
        assert abs(agg["latency_mean"] - 550.0) < 0.01

    def test_missing_values_skipped(self):
        """Missing keys should be ignored in aggregation."""
        results = [
            {"throughput": 1000.0},
            {"latency": 500.0},
        ]
        agg = aggregate_runs(results)
        # Each metric aggregated separately
        assert "throughput_mean" in agg and agg["throughput_mean"] == 1000.0
        assert "latency_mean" in agg and agg["latency_mean"] == 500.0

    def test_non_numeric_ignored_for_stats(self):
        """Non-numeric values should not break mean/std calculation."""
        results = [
            {"throughput": 1000, "status": "ok"},
            {"throughput": 1200, "status": "ok"},
        ]
        agg = aggregate_runs(results)
        assert abs(agg["throughput_mean"] - 1100.0) < 0.01
        assert agg["status"] == "ok"



class TestComputeResourceSummary:
    """Tests for compute_resource_summary function."""

    def test_normal_samples(self):
        """Should compute correct summary statistics."""
        samples = [
            {"cpu_percent": 25.0, "mem_usage_mb": 256.0,
             "blk_read_mb": 10.0, "blk_write_mb": 5.0,
             "net_rx_mb": 1.0, "net_tx_mb": 0.5},
            {"cpu_percent": 30.0, "mem_usage_mb": 280.0,
             "blk_read_mb": 15.0, "blk_write_mb": 8.0,
             "net_rx_mb": 2.0, "net_tx_mb": 1.0},
            {"cpu_percent": 35.0, "mem_usage_mb": 300.0,
             "blk_read_mb": 20.0, "blk_write_mb": 12.0,
             "net_rx_mb": 3.0, "net_tx_mb": 1.5},
        ]
        summary = compute_resource_summary(samples)

        assert abs(summary["avg_cpu_percent"] - 30.0) < 0.01
        assert summary["max_cpu_percent"] == 35.0
        assert summary["min_cpu_percent"] == 25.0
        assert abs(summary["avg_mem_usage_mb"] - 278.67) < 0.1
        assert summary["max_mem_usage_mb"] == 300.0
        assert abs(summary["total_blk_read_mb"] - 10.0) < 0.01    # 20 - 10
        assert abs(summary["total_blk_write_mb"] - 7.0) < 0.01    # 12 - 5

    def test_empty_samples(self):
        """Should return zeros for empty sample list."""
        summary = compute_resource_summary([])
        assert summary["avg_cpu_percent"] == 0.0
        assert summary["max_cpu_percent"] == 0.0
        assert summary["total_blk_read_mb"] == 0.0

    def test_single_sample(self):
        """Should handle single sample correctly."""
        samples = [{"cpu_percent": 50.0, "mem_usage_mb": 500.0,
                     "blk_read_mb": 0.0, "blk_write_mb": 0.0,
                     "net_rx_mb": 0.0, "net_tx_mb": 0.0}]
        summary = compute_resource_summary(samples)
        assert summary["avg_cpu_percent"] == 50.0
        assert summary["max_cpu_percent"] == 50.0
    
    def test_partial_fields_missing(self):
        """Missing resource fields should default to zero."""
        samples = [
            {"cpu_percent": 50.0},  # missing memory, blk, net
            {"mem_usage_mb": 100.0},  # missing cpu
        ]
        summary = compute_resource_summary(samples)
        assert summary["avg_cpu_percent"] == 25.0  # 50/2
        assert summary["avg_mem_usage_mb"] == 50.0  # 100/2
        assert summary["total_blk_read_mb"] == 0.0
        assert summary["total_blk_write_mb"] == 0.0

    def test_identical_samples(self):
        """Multiple identical samples should return correct summary."""
        samples = [
            {"cpu_percent": 20.0, "mem_usage_mb": 200.0,
             "blk_read_mb": 10.0, "blk_write_mb": 5.0,
             "net_rx_mb": 1.0, "net_tx_mb": 0.5},
            {"cpu_percent": 20.0, "mem_usage_mb": 200.0,
             "blk_read_mb": 10.0, "blk_write_mb": 5.0,
             "net_rx_mb": 1.0, "net_tx_mb": 0.5},
        ]
        summary = compute_resource_summary(samples)
        assert summary["avg_cpu_percent"] == 20.0
        assert summary["total_blk_read_mb"] == 0.0  # because last-first = 0
        assert summary["total_blk_write_mb"] == 0.0


class TestCombineMetrics:
    """Tests for combine_metrics function."""

    def test_combines_all(self):
        """Should merge all three dictionaries."""
        ycsb = {"throughput": 1000.0}
        resource = {"avg_cpu_percent": 30.0}
        config_info = {"database": "mongodb", "workload": "a"}

        combined = combine_metrics(ycsb, resource, config_info)

        assert combined["throughput"] == 1000.0
        assert combined["avg_cpu_percent"] == 30.0
        assert combined["database"] == "mongodb"

    def test_no_config_info(self):
        """Should work without config info."""
        combined = combine_metrics(
            {"throughput": 500.0},
            {"avg_cpu_percent": 20.0},
        )
        assert combined["throughput"] == 500.0
        assert combined["avg_cpu_percent"] == 20.0


class TestFormatLatencyUs:
    """Tests for format_latency_us function."""

    def test_microseconds(self):
        """Values < 1000 should be formatted as microseconds."""
        assert format_latency_us(500) == "500 us"

    def test_milliseconds(self):
        """Values 1000-999999 should be formatted as milliseconds."""
        assert format_latency_us(1500) == "1.50 ms"

    def test_seconds(self):
        """Values >= 1,000,000 should be formatted as seconds."""
        assert format_latency_us(1_500_000) == "1.50 s"

    def test_negative(self):
        """Negative values should return N/A."""
        assert format_latency_us(-1) == "N/A"

    def test_zero(self):
        """Zero should be formatted as microseconds."""
        assert format_latency_us(0) == "0 us"
    
    def test_boundary_values(self):
        """Check boundaries between us/ms/s formatting."""
        assert format_latency_us(999) == "999 us"
        assert format_latency_us(1000) == "1.00 ms"
        assert format_latency_us(999_999) == "1000.00 ms"
        assert format_latency_us(1_000_000) == "1.00 s"

    def test_large_values(self):
        """Very large latency values in seconds."""
        assert format_latency_us(10_000_000) == "10.00 s"


class TestFormatThroughput:
    """Tests for format_throughput function."""

    def test_small(self):
        """Values < 1000 should show one decimal."""
        assert format_throughput(500.5) == "500.5 ops/s"

    def test_thousands(self):
        """Values 1000-999999 should use comma formatting."""
        assert format_throughput(12345.0) == "12,345 ops/s"

    def test_millions(self):
        """Values >= 1M should use M suffix."""
        assert format_throughput(1_500_000) == "1.50M ops/s"

    def test_negative(self):
        """Negative values should return N/A."""
        assert format_throughput(-1) == "N/A"
    
    def test_zero_throughput(self):
        """Zero should be formatted as 0 ops/s."""
        assert format_throughput(0) == "0.0 ops/s"

    def test_boundary_millions(self):
        """Check formatting at 1M threshold."""
        assert format_throughput(999_999) == "999,999 ops/s"
        assert format_throughput(1_000_000) == "1.00M ops/s"

    def test_large_millions(self):
        """Very large throughput values."""
        assert format_throughput(123_456_789) == "123.46M ops/s"


