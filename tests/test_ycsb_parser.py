"""Tests for the YCSB output parser."""

import pytest

from src.ycsb_parser import parse_ycsb_output, extract_summary, _make_key, _parse_line


class TestParseYcsbOutput:
    """Tests for the main parse_ycsb_output function."""

    def test_parse_workload_a(self, sample_ycsb_output_a):
        """Should parse Workload A output with READ and UPDATE sections."""
        result = parse_ycsb_output(sample_ycsb_output_a)

        # Overall metrics
        assert result["overall_runtime_ms"] == 10110
        assert abs(result["overall_throughput_ops_per_sec"] - 9891.196834817013) < 0.01

        # Read metrics
        assert result["read_operations"] == 5091
        assert abs(result["read_averagelatency_us"] - 383.24) < 0.01
        assert result["read_minlatency_us"] == 42
        assert result["read_maxlatency_us"] == 230000
        assert result["read_95thpercentilelatency_us"] == 1200
        assert result["read_99thpercentilelatency_us"] == 3500

        # Update metrics
        assert result["update_operations"] == 4909
        assert abs(result["update_averagelatency_us"] - 549.8) < 0.01
        assert result["update_95thpercentilelatency_us"] == 1500
        assert result["update_99thpercentilelatency_us"] == 4200

    def test_parse_workload_b(self, sample_ycsb_output_b):
        """Should parse Workload B output (read-heavy)."""
        result = parse_ycsb_output(sample_ycsb_output_b)

        assert result["read_operations"] == 9505
        assert result["update_operations"] == 495
        assert abs(result["overall_throughput_ops_per_sec"] - 11732.65) < 0.01

    def test_parse_workload_f(self, sample_ycsb_output_f):
        """Should parse Workload F output with READ-MODIFY-WRITE section."""
        result = parse_ycsb_output(sample_ycsb_output_f)

        assert result["read_operations"] == 5000
        assert result["read-modify-write_operations"] == 5000
        assert result["update_operations"] == 5000

    def test_parse_load_output(self, sample_ycsb_load_output):
        """Should parse load phase output with INSERT section."""
        result = parse_ycsb_output(sample_ycsb_load_output)

        assert result["insert_operations"] == 1000000
        assert abs(result["insert_averagelatency_us"] - 230.0) < 0.01
        assert abs(result["overall_throughput_ops_per_sec"] - 40000.0) < 0.01

    def test_parse_empty_string(self):
        """Should return empty dict for empty input."""
        assert parse_ycsb_output("") == {}

    def test_parse_none_input(self):
        """Should return empty dict for None input."""
        assert parse_ycsb_output(None) == {}

    def test_parse_whitespace_only(self):
        """Should return empty dict for whitespace-only input."""
        assert parse_ycsb_output("   \n  \n  ") == {}

    def test_parse_malformed_lines(self):
        """Should skip malformed lines gracefully."""
        output = """\
This is not a YCSB line
[OVERALL], RunTime(ms), 5000
some garbage here
[READ], Operations, 100
incomplete line
"""
        result = parse_ycsb_output(output)
        assert result["overall_runtime_ms"] == 5000
        assert result["read_operations"] == 100
        assert len(result) == 2

    def test_return_ok_as_string(self, sample_ycsb_output_a):
        """Return=OK values should be stored."""
        result = parse_ycsb_output(sample_ycsb_output_a)
        assert result["read_return=ok"] == 5091


class TestMakeKey:
    """Tests for the _make_key helper function."""

    def test_throughput_key(self):
        """Throughput(ops/sec) should normalize correctly."""
        key = _make_key("OVERALL", "Throughput(ops/sec)")
        assert key == "overall_throughput_ops_per_sec"

    def test_runtime_key(self):
        """RunTime(ms) should normalize correctly."""
        key = _make_key("OVERALL", "RunTime(ms)")
        assert key == "overall_runtime_ms"

    def test_average_latency_key(self):
        """AverageLatency(us) should normalize correctly."""
        key = _make_key("READ", "AverageLatency(us)")
        assert key == "read_averagelatency_us"

    def test_percentile_key(self):
        """95thPercentileLatency(us) should normalize correctly."""
        key = _make_key("READ", "95thPercentileLatency(us)")
        assert key == "read_95thpercentilelatency_us"

    def test_operations_key(self):
        """Operations should produce a simple key."""
        key = _make_key("READ", "Operations")
        assert key == "read_operations"


class TestParseLine:
    """Tests for the _parse_line helper function."""

    def test_valid_numeric_line(self):
        """Should parse a valid numeric line."""
        result = _parse_line("[READ], Operations, 5091")
        assert result is not None
        key, value = result
        assert key == "read_operations"
        assert value == 5091.0

    def test_valid_string_value(self):
        """Should handle string values."""
        result = _parse_line("[READ], Return=OK, 5091")
        assert result is not None
        key, value = result
        assert value == 5091.0

    def test_empty_line(self):
        """Should return None for empty lines."""
        assert _parse_line("") is None

    def test_non_bracket_line(self):
        """Should return None for lines not starting with [."""
        assert _parse_line("This is just text") is None

    def test_insufficient_parts(self):
        """Should return None for lines with fewer than 3 comma parts."""
        assert _parse_line("[OVERALL], Something") is None


class TestExtractSummary:
    """Tests for the extract_summary function."""

    def test_workload_a_summary(self, sample_ycsb_output_a):
        """Should extract summary metrics from Workload A."""
        parsed = parse_ycsb_output(sample_ycsb_output_a)
        summary = extract_summary(parsed)

        assert abs(summary["throughput_ops_sec"] - 9891.196834817013) < 0.01
        assert summary["runtime_ms"] == 10110
        assert summary["read_ops"] == 5091.0
        assert summary["update_ops"] == 4909.0
        assert abs(summary["read_avg_latency_us"] - 383.24) < 0.01
        assert summary["read_p95_latency_us"] == 1200
        assert summary["read_p99_latency_us"] == 3500

    def test_empty_parsed(self):
        """Should return zeros for empty parsed dict."""
        summary = extract_summary({})
        assert summary["throughput_ops_sec"] == 0.0
        assert summary["read_ops"] == 0.0
        assert summary["read_p99_latency_us"] == 0.0

    def test_workload_f_rmw_metrics(self, sample_ycsb_output_f):
        """Should extract RMW metrics from Workload F."""
        parsed = parse_ycsb_output(sample_ycsb_output_f)
        summary = extract_summary(parsed)

        assert summary["rmw_ops"] == 5000.0
        assert abs(summary["rmw_avg_latency_us"] - 1200.0) < 0.01
        assert summary["rmw_p95_latency_us"] == 3500
