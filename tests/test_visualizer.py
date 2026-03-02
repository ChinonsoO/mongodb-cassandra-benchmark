"""Tests for the visualizer module."""

from unittest.mock import MagicMock, patch, call
import os

import pytest

from src.analysis.visualizer import (
    plot_throughput_comparison,
    plot_latency_comparison,
    plot_throughput_vs_concurrency,
    plot_latency_vs_concurrency,
    plot_resource_utilization,
    plot_dataset_scaling,
    generate_all_charts,
    COLORS,
)


@pytest.fixture
def sample_workload_data():
    """Sample aggregated workload data."""
    return [
        {
            "database": "mongodb", "workload": "workload_a",
            "throughput_ops_sec_mean": 10000.0, "throughput_ops_sec_std": 500.0,
            "read_avg_latency_us_mean": 380.0, "read_avg_latency_us_std": 20.0,
            "read_p95_latency_us_mean": 1200.0, "read_p95_latency_us_std": 50.0,
            "read_p99_latency_us_mean": 3500.0, "read_p99_latency_us_std": 100.0,
        },
        {
            "database": "cassandra", "workload": "workload_a",
            "throughput_ops_sec_mean": 8000.0, "throughput_ops_sec_std": 400.0,
            "read_avg_latency_us_mean": 450.0, "read_avg_latency_us_std": 25.0,
            "read_p95_latency_us_mean": 1500.0, "read_p95_latency_us_std": 60.0,
            "read_p99_latency_us_mean": 4000.0, "read_p99_latency_us_std": 120.0,
        },
    ]


@pytest.fixture
def sample_concurrency_data():
    """Sample aggregated concurrency data."""
    data = []
    for db in ["mongodb", "cassandra"]:
        for threads in [1, 10, 50, 100]:
            base_tput = 5000 * threads if db == "mongodb" else 4000 * threads
            base_lat = 200 + threads * 5
            data.append({
                "database": db, "threads": threads,
                "workload": "workload_a",
                "throughput_ops_sec_mean": base_tput,
                "throughput_ops_sec_std": base_tput * 0.05,
                "read_avg_latency_us_mean": base_lat,
                "read_avg_latency_us_std": base_lat * 0.1,
                "read_p95_latency_us_mean": base_lat * 3,
                "read_p95_latency_us_std": base_lat * 0.3,
                "read_p99_latency_us_mean": base_lat * 5,
                "read_p99_latency_us_std": base_lat * 0.5,
            })
    return data


class TestDBColors:
    """Tests for database color definitions."""

    def test_mongodb_color(self):
        assert "mongodb" in COLORS

    def test_cassandra_color(self):
        assert "cassandra" in COLORS


class TestPlotThroughputComparison:
    """Tests for throughput comparison chart."""

    @patch("src.analysis.visualizer.plt")
    def test_saves_chart(self, mock_plt, sample_workload_data, tmp_results_dir):
        """Should save chart to output directory."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        output = os.path.join(tmp_results_dir, "throughput.png")
        plot_throughput_comparison(sample_workload_data, output)

        mock_fig.savefig.assert_called_once_with(output, dpi=150, bbox_inches="tight")
        mock_plt.close.assert_called_once_with(mock_fig)

    @patch("src.analysis.visualizer.plt")
    def test_sets_title(self, mock_plt, sample_workload_data, tmp_results_dir):
        """Should set a meaningful title."""
        output = os.path.join(tmp_results_dir, "throughput.png")
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        plot_throughput_comparison(sample_workload_data, output)

        # The function sets title via ax.set_title
        assert mock_ax.set_title.called


class TestPlotLatencyComparison:
    """Tests for latency comparison chart."""

    @patch("src.analysis.visualizer.plt")
    def test_saves_chart(self, mock_plt, sample_workload_data, tmp_results_dir):
        """Should save chart to output directory."""
        mock_fig = MagicMock()
        mock_axes = [MagicMock(), MagicMock(), MagicMock()]
        mock_plt.subplots.return_value = (mock_fig, mock_axes)

        output = os.path.join(tmp_results_dir, "latency.png")
        plot_latency_comparison(sample_workload_data, output)

        mock_fig.savefig.assert_called_once()
        mock_plt.close.assert_called_once_with(mock_fig)


class TestPlotThroughputVsConcurrency:
    """Tests for throughput vs concurrency line chart."""

    @patch("src.analysis.visualizer.plt")
    def test_saves_chart(self, mock_plt, sample_concurrency_data, tmp_results_dir):
        """Should save chart to output directory."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        output = os.path.join(tmp_results_dir, "conc_throughput.png")
        plot_throughput_vs_concurrency(sample_concurrency_data, output)

        mock_fig.savefig.assert_called_once()


class TestPlotLatencyVsConcurrency:
    """Tests for latency vs concurrency line chart."""

    @patch("src.analysis.visualizer.plt")
    def test_saves_chart(self, mock_plt, sample_concurrency_data, tmp_results_dir):
        """Should save chart to output directory."""
        mock_fig = MagicMock()
        mock_ax = MagicMock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)

        output = os.path.join(tmp_results_dir, "conc_latency.png")

        # plot_latency_vs_concurrency uses fig, ax (single axis)
        plot_latency_vs_concurrency(sample_concurrency_data, output)

        mock_fig.savefig.assert_called_once()


class TestPlotResourceUtilization:
    """Tests for resource utilization chart."""

    @patch("src.analysis.visualizer.plt")
    def test_time_series_data(self, mock_plt, tmp_results_dir):
        """Should handle time-series resource data."""
        samples = [
            {"timestamp": 0.0, "cpu_percent": 20.0,
             "mem_usage_mb": 200, "blk_read_mb": 0, "blk_write_mb": 0},
            {"timestamp": 1.0, "cpu_percent": 40.0,
             "mem_usage_mb": 250, "blk_read_mb": 5, "blk_write_mb": 2},
            {"timestamp": 2.0, "cpu_percent": 35.0,
             "mem_usage_mb": 260, "blk_read_mb": 10, "blk_write_mb": 4},
        ]
        output = os.path.join(tmp_results_dir, "resource.png")
        mock_fig = MagicMock()
        mock_axes = [MagicMock(), MagicMock(), MagicMock()]
        mock_plt.subplots.return_value = (mock_fig, mock_axes)

        plot_resource_utilization(samples, output)

        mock_fig.savefig.assert_called_once()


class TestPlotDatasetScaling:
    """Tests for dataset scaling chart."""

    @patch("src.analysis.visualizer.plt")
    def test_saves_chart(self, mock_plt, tmp_results_dir):
        """Should save chart to output directory."""
        data = []
        for db in ["mongodb", "cassandra"]:
            for records in [100000, 1000000, 10000000]:
                data.append({
                    "database": db, "record_count": records,
                    "throughput_ops_sec_mean": 10000.0 / (records / 100000),
                    "throughput_ops_sec_std": 500.0,
                    "read_avg_latency_us_mean": 300 * (records / 100000),
                    "read_avg_latency_us_std": 30.0,
                })
        output = os.path.join(tmp_results_dir, "scaling.png")
        mock_fig = MagicMock()
        mock_axes = (MagicMock(), MagicMock())
        mock_plt.subplots.return_value = (mock_fig, mock_axes)

        plot_dataset_scaling(data, output)

        mock_fig.savefig.assert_called_once()


class TestGenerateAllCharts:
    """Tests for the chart generation dispatcher."""

    @patch("src.analysis.visualizer.plot_throughput_comparison")
    @patch("src.analysis.visualizer.plot_latency_comparison")
    def test_workload_series(self, mock_latency, mock_tput, sample_workload_data,
                              tmp_results_dir):
        """Should dispatch to workload-specific chart functions."""
        all_results = {"workload": sample_workload_data}
        generate_all_charts(all_results, tmp_results_dir)

        mock_tput.assert_called_once()
        mock_latency.assert_called_once()

    @patch("src.analysis.visualizer.plot_throughput_vs_concurrency")
    @patch("src.analysis.visualizer.plot_latency_vs_concurrency")
    def test_concurrency_series(self, mock_lat_conc, mock_tput_conc,
                                 sample_concurrency_data, tmp_results_dir):
        """Should dispatch to concurrency-specific chart functions."""
        all_results = {"concurrency": sample_concurrency_data}
        generate_all_charts(all_results, tmp_results_dir)

        mock_tput_conc.assert_called_once()
        mock_lat_conc.assert_called_once()

    @patch("src.analysis.visualizer.plot_dataset_scaling")
    def test_dataset_series(self, mock_scaling, tmp_results_dir):
        """Should dispatch to dataset scaling chart."""
        data = [{"database": "mongodb", "record_count": 100000,
                  "throughput_ops_sec_mean": 10000}]
        all_results = {"dataset_size": data}
        generate_all_charts(all_results, tmp_results_dir)

        mock_scaling.assert_called_once()

    def test_empty_results(self, tmp_results_dir):
        """Should handle empty results gracefully."""
        generate_all_charts({}, tmp_results_dir)
        # Should not raise
