"""Tests for the experiment runner module."""

import json
from unittest.mock import MagicMock, patch, call

import pytest

from src.config import DatabaseConfig, WorkloadConfig, RunConfig, ExperimentConfig
from src.experiment_runner import ExperimentRunner


@pytest.fixture
def mock_docker_manager():
    """Create a mock DockerManager."""
    dm = MagicMock()
    dm.client = MagicMock()
    return dm


@pytest.fixture
def mock_ycsb_runner(sample_ycsb_output_a, sample_ycsb_load_output):
    """Create a mock YCSBRunner that returns sample output."""
    runner = MagicMock()
    runner.load.return_value = sample_ycsb_load_output
    runner.run.return_value = sample_ycsb_output_a
    return runner


@pytest.fixture
def sample_run_config():
    """Create a sample RunConfig."""
    db = DatabaseConfig(
        name="mongodb",
        host="localhost",
        port=27017,
        container_name="ycsb-mongodb",
        ycsb_binding="mongodb",
        connection_properties={"mongodb.url": "mongodb://localhost:27017/ycsb?w=1"},
    )
    wl = WorkloadConfig(
        name="workload_a",
        file="workloads/workload_a.properties",
        label="Workload A (Update Heavy)",
    )
    return RunConfig(
        database=db,
        workload=wl,
        threads=10,
        record_count=1000000,
        operation_count=100000,
        warmup_operation_count=1000,
        series_name="workload",
        dataset_label="1 GB",
        repetition=1,
    )


@pytest.fixture
def sample_experiment_config(sample_run_config):
    """Create a sample ExperimentConfig."""
    return ExperimentConfig(
        databases={"mongodb": sample_run_config.database},
        series={"workload": [sample_run_config]},
        repetitions=1,
        ycsb_path="ycsb-0.17.0",
    )


class TestExperimentRunnerInit:
    """Tests for ExperimentRunner initialization."""

    def test_creates_results_dirs(self, tmp_results_dir, sample_experiment_config,
                                   mock_docker_manager, mock_ycsb_runner):
        """Should create raw and analysis directories."""
        runner = ExperimentRunner(
            config=sample_experiment_config,
            docker_manager=mock_docker_manager,
            ycsb_runner=mock_ycsb_runner,
            results_dir=tmp_results_dir,
        )
        import os
        assert os.path.exists(os.path.join(tmp_results_dir, "raw"))
        assert os.path.exists(os.path.join(tmp_results_dir, "analysis"))


class TestRunSingle:
    """Tests for single benchmark run execution."""

    @patch("src.experiment_runner.ResourceMonitor")
    @patch("src.experiment_runner.setup_database")
    @patch("src.experiment_runner.reset_database")
    def test_successful_run(
        self, mock_reset, mock_setup, mock_monitor_cls,
        tmp_results_dir, sample_experiment_config,
        mock_docker_manager, mock_ycsb_runner, sample_run_config,
    ):
        """Should execute all steps and return success result."""
        # Set up resource monitor mock
        mock_monitor = MagicMock()
        mock_monitor.stop.return_value = [
            {"cpu_percent": 25.0, "mem_usage_mb": 256.0,
             "blk_read_mb": 10.0, "blk_write_mb": 5.0,
             "net_rx_mb": 1.0, "net_tx_mb": 0.5},
        ]
        mock_monitor_cls.return_value = mock_monitor

        runner = ExperimentRunner(
            config=sample_experiment_config,
            docker_manager=mock_docker_manager,
            ycsb_runner=mock_ycsb_runner,
            results_dir=tmp_results_dir,
        )

        result = runner.run_single(sample_run_config)

        # Verify workflow order
        mock_reset.assert_called_once_with("mongodb", "localhost", 27017)
        mock_setup.assert_called_once_with("mongodb", "localhost", 27017)
        assert mock_ycsb_runner.load.called
        assert mock_ycsb_runner.run.called
        mock_monitor.start.assert_called_once()
        mock_monitor.stop.assert_called_once()

        # Verify result
        assert result["status"] == "success"
        assert result["database"] == "mongodb"
        assert result["workload"] == "workload_a"
        assert result["threads"] == 10

    @patch("src.experiment_runner.ResourceMonitor")
    @patch("src.experiment_runner.setup_database")
    @patch("src.experiment_runner.reset_database")
    def test_ycsb_properties_passed(
        self, mock_reset, mock_setup, mock_monitor_cls,
        tmp_results_dir, sample_experiment_config,
        mock_docker_manager, mock_ycsb_runner, sample_run_config,
    ):
        """Should pass correct YCSB properties including thread count."""
        mock_monitor = MagicMock()
        mock_monitor.stop.return_value = []
        mock_monitor_cls.return_value = mock_monitor

        runner = ExperimentRunner(
            config=sample_experiment_config,
            docker_manager=mock_docker_manager,
            ycsb_runner=mock_ycsb_runner,
            results_dir=tmp_results_dir,
        )

        runner.run_single(sample_run_config)

        # Check load phase properties
        load_call = mock_ycsb_runner.load.call_args
        props = load_call.kwargs.get("properties") or load_call[1].get("properties")
        assert props["recordcount"] == "1000000"
        assert props["operationcount"] == "100000"
        assert props["threadcount"] == "10"

    @patch("src.experiment_runner.ResourceMonitor")
    @patch("src.experiment_runner.setup_database")
    @patch("src.experiment_runner.reset_database")
    def test_error_handling(
        self, mock_reset, mock_setup, mock_monitor_cls,
        tmp_results_dir, sample_experiment_config,
        mock_docker_manager, mock_ycsb_runner, sample_run_config,
    ):
        """Should handle errors gracefully and mark result as error."""
        mock_reset.side_effect = RuntimeError("Database connection failed")

        runner = ExperimentRunner(
            config=sample_experiment_config,
            docker_manager=mock_docker_manager,
            ycsb_runner=mock_ycsb_runner,
            results_dir=tmp_results_dir,
        )

        result = runner.run_single(sample_run_config)

        assert result["status"] == "error"
        assert "Database connection failed" in result["error"]

    @patch("src.experiment_runner.ResourceMonitor")
    @patch("src.experiment_runner.setup_database")
    @patch("src.experiment_runner.reset_database")
    def test_saves_raw_result(
        self, mock_reset, mock_setup, mock_monitor_cls,
        tmp_results_dir, sample_experiment_config,
        mock_docker_manager, mock_ycsb_runner, sample_run_config,
    ):
        """Should save raw result to JSON file."""
        mock_monitor = MagicMock()
        mock_monitor.stop.return_value = []
        mock_monitor_cls.return_value = mock_monitor

        runner = ExperimentRunner(
            config=sample_experiment_config,
            docker_manager=mock_docker_manager,
            ycsb_runner=mock_ycsb_runner,
            results_dir=tmp_results_dir,
        )

        result = runner.run_single(sample_run_config)

        import os
        raw_dir = os.path.join(tmp_results_dir, "raw")
        files = os.listdir(raw_dir)
        assert len(files) == 1
        assert files[0].endswith(".json")

        with open(os.path.join(raw_dir, files[0])) as f:
            saved = json.load(f)
        assert saved["database"] == "mongodb"


class TestRunSeries:
    """Tests for series execution."""

    @patch("src.experiment_runner.ResourceMonitor")
    @patch("src.experiment_runner.setup_database")
    @patch("src.experiment_runner.reset_database")
    def test_runs_all_configs_in_series(
        self, mock_reset, mock_setup, mock_monitor_cls,
        tmp_results_dir, mock_docker_manager, mock_ycsb_runner,
    ):
        """Should run all configurations in a series."""
        mock_monitor = MagicMock()
        mock_monitor.stop.return_value = []
        mock_monitor_cls.return_value = mock_monitor

        db = DatabaseConfig(
            name="mongodb", host="localhost", port=27017,
            container_name="ycsb-mongodb", ycsb_binding="mongodb",
        )
        wl = WorkloadConfig(name="wl_a", file="wl_a.properties", label="A")

        runs = [
            RunConfig(database=db, workload=wl, threads=1,
                      record_count=1000, operation_count=1000, repetition=i)
            for i in range(1, 4)
        ]

        config = ExperimentConfig(
            databases={"mongodb": db},
            series={"test_series": runs},
            repetitions=3,
            ycsb_path="ycsb-0.17.0",
        )

        runner = ExperimentRunner(
            config=config,
            docker_manager=mock_docker_manager,
            ycsb_runner=mock_ycsb_runner,
            results_dir=tmp_results_dir,
        )

        results = runner.run_series("test_series")
        assert len(results) == 3
    
    

    def test_unknown_series_raises(
        self, tmp_results_dir, sample_experiment_config,
        mock_docker_manager, mock_ycsb_runner,
    ):
        """Should raise ValueError for unknown series name."""
        runner = ExperimentRunner(
            config=sample_experiment_config,
            docker_manager=mock_docker_manager,
            ycsb_runner=mock_ycsb_runner,
            results_dir=tmp_results_dir,
        )

        with pytest.raises(ValueError, match="Unknown series"):
            runner.run_series("nonexistent_series")


class TestAggregateSeriesResults:
    """Tests for result aggregation."""

    def test_aggregates_repetitions(
        self, tmp_results_dir, sample_experiment_config,
        mock_docker_manager, mock_ycsb_runner,
    ):
        """Should aggregate multiple repetitions into mean/std."""
        runner = ExperimentRunner(
            config=sample_experiment_config,
            docker_manager=mock_docker_manager,
            ycsb_runner=mock_ycsb_runner,
            results_dir=tmp_results_dir,
        )

        results = [
            {
                "database": "mongodb", "workload": "wl_a",
                "threads": 10, "record_count": 1000000,
                "throughput_ops_sec": 10000.0,
                "read_avg_latency_us": 500.0,
                "status": "success", "repetition": 1,
            },
            {
                "database": "mongodb", "workload": "wl_a",
                "threads": 10, "record_count": 1000000,
                "throughput_ops_sec": 12000.0,
                "read_avg_latency_us": 450.0,
                "status": "success", "repetition": 2,
            },
        ]

        aggregated = runner.aggregate_series_results(results)
        assert len(aggregated) == 1
        assert abs(aggregated[0]["throughput_ops_sec_mean"] - 11000.0) < 0.01

    def test_skips_error_results(
        self, tmp_results_dir, sample_experiment_config,
        mock_docker_manager, mock_ycsb_runner,
    ):
        """Should skip results with error status."""
        runner = ExperimentRunner(
            config=sample_experiment_config,
            docker_manager=mock_docker_manager,
            ycsb_runner=mock_ycsb_runner,
            results_dir=tmp_results_dir,
        )

        results = [
            {"database": "mongodb", "workload": "wl_a", "threads": 10,
             "record_count": 1000000, "throughput_ops_sec": 10000.0,
             "status": "success", "repetition": 1},
            {"database": "mongodb", "workload": "wl_a", "threads": 10,
             "record_count": 1000000, "status": "error", "repetition": 2},
        ]

        aggregated = runner.aggregate_series_results(results)
        assert len(aggregated) == 1
    
    