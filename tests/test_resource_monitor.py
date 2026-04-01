"""Tests for the resource monitor module."""

import time
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.resource_monitor import (
    ResourceMonitor,
    _calculate_cpu_budget,
    _calculate_cpu_percent,
    _calculate_blkio,
    _count_cpuset_cpus,
    _calculate_network,
)


class TestCalculateCpuPercent:
    """Tests for CPU percentage calculation."""

    def test_normal_calculation(self, sample_docker_stats):
        """Should compute correct CPU percentage.

        cpu_delta = 500M - 400M = 100M
        system_delta = 10B - 9B = 1B
        num_cpus = 4
        expected = (100M/1B) * 4 * 100 = 40%
        """
        result = _calculate_cpu_percent(sample_docker_stats)
        assert abs(result - 40.0) < 0.01

    def test_zero_system_delta(self):
        """Should return 0% when system_delta is 0."""
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 500},
                "system_cpu_usage": 1000,
                "online_cpus": 2,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 400},
                "system_cpu_usage": 1000,
            },
        }
        assert _calculate_cpu_percent(stats) == 0.0

    def test_empty_stats(self):
        """Should return 0% for empty stats."""
        assert _calculate_cpu_percent({}) == 0.0

    def test_missing_fields(self):
        """Should return 0% when fields are missing."""
        stats = {"cpu_stats": {}, "precpu_stats": {}}
        assert _calculate_cpu_percent(stats) == 0.0


class TestCalculateCpuBudget:
    """Tests for CPU budget normalization."""

    def test_uses_nano_cpus_when_available(self, sample_docker_stats):
        attrs = {"HostConfig": {"NanoCpus": 2_000_000_000}}
        assert _calculate_cpu_budget(sample_docker_stats, attrs) == 2.0

    def test_uses_cpuset_when_smaller_than_online_cpu_count(self, sample_docker_stats):
        attrs = {"HostConfig": {"CpusetCpus": "0-1"}}
        assert _calculate_cpu_budget(sample_docker_stats, attrs) == 2.0

    def test_falls_back_to_online_cpu_count(self, sample_docker_stats):
        assert _calculate_cpu_budget(sample_docker_stats) == 4.0


class TestCountCpusetCpus:
    """Tests for cpuset parsing."""

    def test_counts_ranges_and_single_values(self):
        assert _count_cpuset_cpus("0-1,4,6-7") == 5

    def test_handles_empty_or_invalid_values(self):
        assert _count_cpuset_cpus("") == 0
        assert _count_cpuset_cpus("bad") == 0


class TestCalculateBlkio:
    """Tests for block I/O calculation."""

    def test_normal_blkio(self, sample_docker_stats):
        """Should return correct read and write bytes."""
        read_bytes, write_bytes = _calculate_blkio(sample_docker_stats)
        assert read_bytes == 50 * 1024 * 1024
        assert write_bytes == 30 * 1024 * 1024

    def test_empty_blkio(self):
        """Should return zeros for empty blkio."""
        assert _calculate_blkio({}) == (0, 0)

    def test_null_io_bytes(self):
        """Should return zeros when io_service_bytes_recursive is None."""
        stats = {"blkio_stats": {"io_service_bytes_recursive": None}}
        assert _calculate_blkio(stats) == (0, 0)


class TestCalculateNetwork:
    """Tests for network I/O calculation."""

    def test_normal_network(self, sample_docker_stats):
        """Should return correct rx and tx bytes."""
        rx, tx = _calculate_network(sample_docker_stats)
        assert rx == 5 * 1024 * 1024
        assert tx == 2 * 1024 * 1024

    def test_empty_networks(self):
        """Should return zeros for empty networks."""
        assert _calculate_network({}) == (0, 0)

    def test_multiple_interfaces(self):
        """Should sum bytes across all interfaces."""
        stats = {
            "networks": {
                "eth0": {"rx_bytes": 100, "tx_bytes": 50},
                "eth1": {"rx_bytes": 200, "tx_bytes": 100},
            }
        }
        rx, tx = _calculate_network(stats)
        assert rx == 300
        assert tx == 150


class TestResourceMonitorParseStats:
    """Tests for the _parse_stats static method."""

    def test_parse_docker_stats(self, sample_docker_stats):
        """Should produce a structured sample from raw Docker stats."""
        sample = ResourceMonitor._parse_stats(sample_docker_stats)

        assert "timestamp" in sample
        assert abs(sample["cpu_percent"] - 10.0) < 0.01
        assert abs(sample["mem_usage_mb"] - 256.0) < 0.01
        assert abs(sample["mem_limit_mb"] - 2048.0) < 0.01
        assert abs(sample["mem_percent"] - 12.5) < 0.01
        assert abs(sample["blk_read_mb"] - 50.0) < 0.01
        assert abs(sample["blk_write_mb"] - 30.0) < 0.01
        assert abs(sample["net_rx_mb"] - 5.0) < 0.01
        assert abs(sample["net_tx_mb"] - 2.0) < 0.01

    def test_parse_docker_stats_normalizes_to_container_cpu_budget(
        self, sample_docker_stats
    ):
        """Should normalize CPU percent against the allowed CPU budget."""
        sample = ResourceMonitor._parse_stats(sample_docker_stats, cpu_budget=2.0)
        assert abs(sample["cpu_percent"] - 20.0) < 0.01


class TestResourceMonitorLifecycle:
    """Tests for monitor start/stop lifecycle."""

    def test_start_stop(self, sample_docker_stats):
        """Should collect samples between start and stop."""
        mock_container = MagicMock()
        mock_container.stats.return_value = sample_docker_stats

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        monitor = ResourceMonitor(
            container_name="test-container",
            docker_client=mock_client,
            interval=0.05,
        )

        monitor.start()
        time.sleep(0.2)  # Allow a few samples to be collected
        samples = monitor.stop()

        assert len(samples) > 0
        assert all("cpu_percent" in s for s in samples)
        assert all("mem_usage_mb" in s for s in samples)

    def test_stop_without_start(self):
        """Should return empty list if never started."""
        monitor = ResourceMonitor("test-container", docker_client=MagicMock())
        samples = monitor.stop()
        assert samples == []

    def test_double_start_raises(self, sample_docker_stats):
        """Should raise RuntimeError if already running."""
        mock_container = MagicMock()
        mock_container.stats.return_value = sample_docker_stats

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        monitor = ResourceMonitor(
            container_name="test",
            docker_client=mock_client,
            interval=0.1,
        )

        monitor.start()
        try:
            with pytest.raises(RuntimeError, match="already running"):
                monitor.start()
        finally:
            monitor.stop()

    def test_get_samples_during_monitoring(self, sample_docker_stats):
        """Should return partial samples while monitoring."""
        mock_container = MagicMock()
        mock_container.stats.return_value = sample_docker_stats

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        monitor = ResourceMonitor(
            container_name="test",
            docker_client=mock_client,
            interval=0.05,
        )

        monitor.start()
        time.sleep(0.15)
        partial = monitor.get_samples()
        time.sleep(0.15)
        final = monitor.stop()

        assert len(partial) > 0
        assert len(final) >= len(partial)

    def test_container_not_found(self):
        """Should handle container not found gracefully."""
        mock_client = MagicMock()
        mock_client.containers.get.side_effect = Exception("not found")

        monitor = ResourceMonitor(
            container_name="nonexistent",
            docker_client=mock_client,
            interval=0.05,
        )

        monitor.start()
        time.sleep(0.1)
        samples = monitor.stop()

        # Should have no samples since container wasn't found
        assert len(samples) == 0
