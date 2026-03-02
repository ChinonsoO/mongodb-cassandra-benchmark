"""Tests for the configuration module."""

import pytest

from src.config import (
    DatabaseConfig,
    ExperimentConfig,
    RunConfig,
    WorkloadConfig,
    load_experiment_config,
    records_for_size_mb,
)


class TestRecordsForSizeMb:
    """Tests for the records_for_size_mb function."""

    def test_100mb(self):
        """100 MB should yield ~104,857 records at 1000 bytes each."""
        result = records_for_size_mb(100, 1000)
        assert result == 104857

    def test_1gb(self):
        """1 GB (1024 MB) should yield ~1,073,741 records."""
        result = records_for_size_mb(1024, 1000)
        assert result == 1073741

    def test_10gb(self):
        """10 GB should yield ~10,737,418 records."""
        result = records_for_size_mb(10240, 1000)
        assert result == 10737418

    def test_custom_record_size(self):
        """Custom bytes_per_record should scale inversely."""
        result_500 = records_for_size_mb(100, 500)
        result_1000 = records_for_size_mb(100, 1000)
        # Floor division may differ by ±1, so check approximate doubling
        assert abs(result_500 - result_1000 * 2) <= 1

    def test_negative_size_raises(self):
        """Negative size should raise ValueError."""
        with pytest.raises(ValueError, match="size_mb must be positive"):
            records_for_size_mb(-1)

    def test_zero_bytes_per_record_raises(self):
        """Zero bytes per record should raise ValueError."""
        with pytest.raises(ValueError, match="bytes_per_record must be positive"):
            records_for_size_mb(100, 0)


class TestDatabaseConfig:
    """Tests for the DatabaseConfig dataclass."""

    def test_creation(self):
        """Should create a DatabaseConfig with all fields."""
        db = DatabaseConfig(
            name="mongodb",
            host="localhost",
            port=27017,
            container_name="ycsb-mongodb",
            ycsb_binding="mongodb",
            connection_properties={"mongodb.url": "mongodb://localhost:27017/ycsb"},
        )
        assert db.name == "mongodb"
        assert db.port == 27017
        assert db.container_name == "ycsb-mongodb"

    def test_default_connection_properties(self):
        """Connection properties should default to empty dict."""
        db = DatabaseConfig(
            name="test", host="localhost", port=1234,
            container_name="test", ycsb_binding="test",
        )
        assert db.connection_properties == {}


class TestRunConfig:
    """Tests for the RunConfig dataclass."""

    def test_run_id(self):
        """run_id should encode all key configuration parameters."""
        db = DatabaseConfig(
            name="mongodb", host="localhost", port=27017,
            container_name="ycsb-mongodb", ycsb_binding="mongodb",
        )
        wl = WorkloadConfig(name="workload_a", file="wl_a.properties", label="WL A")
        run = RunConfig(
            database=db, workload=wl, threads=10,
            record_count=1000000, operation_count=100000, repetition=2,
        )
        assert run.run_id == "mongodb_workload_a_t10_r1000000_rep2"

    def test_defaults(self):
        """Default values should be set correctly."""
        db = DatabaseConfig(
            name="test", host="localhost", port=1234,
            container_name="test", ycsb_binding="test",
        )
        wl = WorkloadConfig(name="test", file="test.properties", label="test")
        run = RunConfig(
            database=db, workload=wl, threads=1,
            record_count=1000, operation_count=1000,
        )
        assert run.warmup_operation_count == 1000
        assert run.series_name == ""
        assert run.repetition == 1


class TestLoadExperimentConfig:
    """Tests for load_experiment_config function."""

    def test_load_valid_config(self, sample_experiment_yaml):
        """Should successfully load a valid YAML config."""
        config = load_experiment_config(sample_experiment_yaml)

        assert isinstance(config, ExperimentConfig)
        assert "mongodb" in config.databases
        assert "cassandra" in config.databases
        assert config.repetitions == 2

    def test_databases_parsed_correctly(self, sample_experiment_yaml):
        """Database configs should have correct properties."""
        config = load_experiment_config(sample_experiment_yaml)

        mongo = config.databases["mongodb"]
        assert mongo.host == "localhost"
        assert mongo.port == 27017
        assert mongo.container_name == "ycsb-mongodb"
        assert mongo.ycsb_binding == "mongodb"

        cass = config.databases["cassandra"]
        assert cass.port == 9042
        assert cass.ycsb_binding == "cassandra-cql"

    def test_series_expanded(self, sample_experiment_yaml):
        """Series should be expanded into RunConfig lists."""
        config = load_experiment_config(sample_experiment_yaml)

        assert "workload" in config.series
        assert "concurrency" in config.series

        # Workload series: 2 databases x 2 workloads x 2 repetitions = 8 runs
        workload_runs = config.series["workload"]
        assert len(workload_runs) == 8
        assert all(isinstance(r, RunConfig) for r in workload_runs)

    def test_concurrency_series(self, sample_experiment_yaml):
        """Concurrency series should have correct thread levels."""
        config = load_experiment_config(sample_experiment_yaml)

        concurrency_runs = config.series["concurrency"]
        # 2 databases x 1 workload x 3 thread levels x 2 repetitions = 12 runs
        assert len(concurrency_runs) == 12

        thread_values = {r.threads for r in concurrency_runs}
        assert thread_values == {1, 10, 50}

    def test_file_not_found(self):
        """Should raise FileNotFoundError for missing config."""
        with pytest.raises(FileNotFoundError):
            load_experiment_config("nonexistent.yaml")

    def test_empty_config(self, tmp_path):
        """Should raise ValueError for empty config file."""
        empty_file = tmp_path / "empty.yaml"
        empty_file.write_text("")
        with pytest.raises(ValueError):
            load_experiment_config(str(empty_file))

    def test_invalid_yaml(self, tmp_path):
        """Should raise ValueError for non-mapping YAML."""
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text("just a string")
        with pytest.raises(ValueError):
            load_experiment_config(str(bad_file))
