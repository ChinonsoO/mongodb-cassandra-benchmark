"""Experiment configuration management.

Loads experiment definitions from YAML and provides structured
configuration objects for the benchmark suite.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Approximate bytes per YCSB record (10 fields x 100 bytes + key overhead)
DEFAULT_BYTES_PER_RECORD = 1000


@dataclass
class DatabaseConfig:
    """Configuration for a single database target."""

    name: str
    host: str
    port: int
    container_name: str
    ycsb_binding: str
    connection_properties: dict[str, str] = field(default_factory=dict)


@dataclass
class WorkloadConfig:
    """Configuration for a YCSB workload."""

    name: str
    file: str
    label: str


@dataclass
class RunConfig:
    """Configuration for a single benchmark run."""

    database: DatabaseConfig
    workload: WorkloadConfig
    threads: int
    record_count: int
    operation_count: int
    warmup_operation_count: int = 1000
    series_name: str = ""
    dataset_label: str = ""
    repetition: int = 1

    @property
    def run_id(self) -> str:
        """Unique identifier for this run."""
        return (
            f"{self.database.name}_{self.workload.name}_"
            f"t{self.threads}_r{self.record_count}_rep{self.repetition}"
        )


@dataclass
class ExperimentConfig:
    """Full experiment configuration."""

    databases: dict[str, DatabaseConfig]
    series: dict[str, list[RunConfig]]
    repetitions: int
    ycsb_path: str
    java_home: str = ""
    results_dir: str = "results"


def records_for_size_mb(size_mb: int, bytes_per_record: int = DEFAULT_BYTES_PER_RECORD) -> int:
    """Calculate the number of YCSB records needed for a target dataset size.

    Args:
        size_mb: Target dataset size in megabytes.
        bytes_per_record: Approximate size of each YCSB record in bytes.

    Returns:
        Number of records needed.

    Raises:
        ValueError: If size_mb or bytes_per_record is not positive.
    """
    if size_mb <= 0:
        raise ValueError(f"size_mb must be positive, got {size_mb}")
    if bytes_per_record <= 0:
        raise ValueError(f"bytes_per_record must be positive, got {bytes_per_record}")
    return (size_mb * 1024 * 1024) // bytes_per_record


def load_experiment_config(yaml_path: str) -> ExperimentConfig:
    """Load experiment configuration from a YAML file.

    Args:
        yaml_path: Path to the experiment YAML configuration file.

    Returns:
        ExperimentConfig with all series expanded into RunConfig lists.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        ValueError: If required configuration fields are missing.
    """
    yaml_path = Path(yaml_path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {yaml_path}")

    with open(yaml_path, "r") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raise ValueError("Empty configuration file")

    if not isinstance(raw, dict):
        raise ValueError(f"Configuration must be a YAML mapping, got: {type(raw).__name__}")

    # Parse databases
    databases = _parse_databases(raw.get("databases", {}))
    if not databases:
        raise ValueError("No databases defined in configuration")

    # Parse global settings
    repetitions = raw.get("repetitions", 3)
    ycsb_path = raw.get("ycsb", {}).get("path", "ycsb-0.17.0")
    java_home = raw.get("ycsb", {}).get("java_home", "")
    bytes_per_record = raw.get("ycsb", {}).get("bytes_per_record", DEFAULT_BYTES_PER_RECORD)

    # Parse dataset sizes
    dataset_sizes = raw.get("dataset_sizes", {})

    # Parse baseline
    baseline = raw.get("baseline", {})
    baseline_dataset = baseline.get("dataset", "medium")
    baseline_threads = baseline.get("threads", 10)
    baseline_operation_count = baseline.get("operation_count", 100000)
    warmup_op_count = baseline.get("warmup_operation_count", 1000)

    # Parse and expand series
    series_raw = raw.get("series", {})
    all_series = {}

    for series_name, series_def in series_raw.items():
        runs = _expand_series(
            series_name=series_name,
            series_def=series_def,
            databases=databases,
            dataset_sizes=dataset_sizes,
            baseline_dataset=baseline_dataset,
            baseline_threads=baseline_threads,
            baseline_operation_count=baseline_operation_count,
            warmup_op_count=warmup_op_count,
            bytes_per_record=bytes_per_record,
            repetitions=repetitions,
        )
        all_series[series_name] = runs

    return ExperimentConfig(
        databases=databases,
        series=all_series,
        repetitions=repetitions,
        ycsb_path=ycsb_path,
        java_home=java_home,
    )


def _parse_databases(db_raw: dict[str, Any]) -> dict[str, DatabaseConfig]:
    """Parse database configurations from raw YAML."""
    databases = {}
    for name, cfg in db_raw.items():
        databases[name] = DatabaseConfig(
            name=name,
            host=cfg.get("host", "localhost"),
            port=cfg.get("port", 27017),
            container_name=cfg.get("container_name", f"ycsb-{name}"),
            ycsb_binding=cfg.get("ycsb_binding", name),
            connection_properties={
                str(k): str(v)
                for k, v in cfg.get("connection_properties", {}).items()
            },
        )
    return databases


def _expand_series(
    series_name: str,
    series_def: dict[str, Any],
    databases: dict[str, DatabaseConfig],
    dataset_sizes: dict[str, Any],
    baseline_dataset: str,
    baseline_threads: int,
    baseline_operation_count: int,
    warmup_op_count: int,
    bytes_per_record: int,
    repetitions: int,
) -> list[RunConfig]:
    """Expand a series definition into individual RunConfig objects."""
    runs: list[RunConfig] = []

    workloads = [
        WorkloadConfig(
            name=w["name"],
            file=w["file"],
            label=w["label"],
        )
        for w in series_def.get("workloads", [])
    ]

    operation_count = series_def.get("operation_count", baseline_operation_count)

    # Determine thread levels
    thread_levels = series_def.get("thread_levels")
    if thread_levels is None:
        thread_levels = [series_def.get("threads", baseline_threads)]

    # Determine dataset configurations
    dataset_keys = series_def.get("datasets")
    if dataset_keys is None:
        ds_key = series_def.get("dataset", baseline_dataset)
        dataset_keys = [ds_key]

    for db_name, db_config in databases.items():
        for workload in workloads:
            for ds_key in dataset_keys:
                ds_info = dataset_sizes.get(ds_key, {})
                record_count = ds_info.get("record_count", 1000000)
                dataset_label = ds_info.get("label", ds_key)

                for threads in thread_levels:
                    for rep in range(1, repetitions + 1):
                        runs.append(
                            RunConfig(
                                database=db_config,
                                workload=workload,
                                threads=threads,
                                record_count=record_count,
                                operation_count=operation_count,
                                warmup_operation_count=warmup_op_count,
                                series_name=series_name,
                                dataset_label=dataset_label,
                                repetition=rep,
                            )
                        )

    return runs


def get_total_runs(config: ExperimentConfig) -> int:
    """Get the total number of benchmark runs in an experiment."""
    return sum(len(runs) for runs in config.series.values())


def get_series_names(config: ExperimentConfig) -> list[str]:
    """Get the names of all experiment series."""
    return list(config.series.keys())
