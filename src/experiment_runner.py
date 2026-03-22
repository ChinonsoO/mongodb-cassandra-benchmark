"""Experiment orchestration - runs all benchmark configurations.

Ties together Docker management, database setup, YCSB execution,
resource monitoring, and result collection.
"""

import json
import logging
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

from src.config import ExperimentConfig, RunConfig, load_experiment_config
from src.db_setup import reset_database, setup_database
from src.docker_manager import DockerManager
from src.metrics import aggregate_runs, combine_metrics, compute_resource_summary
from src.resource_monitor import ResourceMonitor
from src.ycsb_parser import extract_summary, parse_ycsb_output
from src.ycsb_runner import YCSBRunner

logger = logging.getLogger(__name__)


class ExperimentRunner:
    """Orchestrate complete benchmark experiments.

    Manages the full lifecycle of each benchmark run:
    reset DB -> load data -> warmup -> start monitoring -> run workload ->
    stop monitoring -> parse results -> save output.
    """

    def __init__(
        self,
        config: ExperimentConfig,
        docker_manager: DockerManager,
        ycsb_runner: YCSBRunner,
        results_dir: str = "results",
    ):
        """Initialize ExperimentRunner.

        Args:
            config: Experiment configuration with all series and run configs.
            docker_manager: Docker container manager instance.
            ycsb_runner: YCSB command runner instance.
            results_dir: Base directory for storing results.
        """
        self.config = config
        self.docker_manager = docker_manager
        self.ycsb_runner = ycsb_runner
        self.results_dir = Path(results_dir)
        self._ensure_results_dirs()

    def _ensure_results_dirs(self) -> None:
        """Create results directories if they don't exist."""
        (self.results_dir / "raw").mkdir(parents=True, exist_ok=True)
        (self.results_dir / "analysis").mkdir(parents=True, exist_ok=True)

    def run_single(self, run_config: RunConfig) -> dict[str, Any]:
        """Execute a single benchmark run.

        Follows the pipeline: reset -> load -> warmup -> monitor+run -> parse -> save.

        Args:
            run_config: Configuration for this specific run.

        Returns:
            Dictionary with all collected metrics and metadata.
        """
        run_id = run_config.run_id
        db = run_config.database
        logger.info(f"=== Starting run: {run_id} ===")
        logger.info(
            f"  Database: {db.name}, Workload: {run_config.workload.label}, "
            f"Threads: {run_config.threads}, Records: {run_config.record_count}"
        )

        result: dict[str, Any] = {
            "run_id": run_id,
            "database": db.name,
            "workload": run_config.workload.name,
            "workload_label": run_config.workload.label,
            "threads": run_config.threads,
            "record_count": run_config.record_count,
            "operation_count": run_config.operation_count,
            "series": run_config.series_name,
            "dataset_label": run_config.dataset_label,
            "repetition": run_config.repetition,
        }

        try:
            # Step 1: Reset database
            logger.info(f"  Step 1: Resetting {db.name} database...")
            reset_database(db.name, db.host, db.port)

            # Step 2: Set up database schema (Cassandra needs keyspace/table)
            logger.info(f"  Step 2: Setting up {db.name} schema...")
            setup_database(db.name, db.host, db.port)

            # Step 3: Build YCSB properties
            ycsb_props = dict(db.connection_properties)
            ycsb_props["recordcount"] = str(run_config.record_count)
            ycsb_props["operationcount"] = str(run_config.operation_count)
            ycsb_props["threadcount"] = str(run_config.threads)

            # Step 4: YCSB load phase
            logger.info(f"  Step 3: Loading data ({run_config.record_count} records)...")
            load_start = time.time()
            load_output = self.ycsb_runner.load(
                binding=db.ycsb_binding,
                workload_file=run_config.workload.file,
                properties=ycsb_props,
            )
            load_duration = time.time() - load_start
            result["load_duration_sec"] = load_duration
            logger.info(f"  Data loaded in {load_duration:.1f}s")

            # Step 5: Warmup run (small operation count, results discarded)
            if run_config.warmup_operation_count > 0:
                logger.info(f"  Step 4: Warmup ({run_config.warmup_operation_count} ops)...")
                warmup_props = dict(ycsb_props)
                warmup_props["operationcount"] = str(run_config.warmup_operation_count)
                self.ycsb_runner.run(
                    binding=db.ycsb_binding,
                    workload_file=run_config.workload.file,
                    properties=warmup_props,
                )

            # Step 6: Start resource monitoring
            logger.info("  Step 5: Starting resource monitoring...")
            monitor = ResourceMonitor(
                container_name=db.container_name,
                docker_client=self.docker_manager.client,
                interval=1.0,
            )
            monitor.start()

            # Step 7: Run the actual workload
            logger.info(f"  Step 6: Running workload ({run_config.operation_count} ops)...")
            run_start = time.time()
            run_output = self.ycsb_runner.run(
                binding=db.ycsb_binding,
                workload_file=run_config.workload.file,
                properties=ycsb_props,
            )
            run_duration = time.time() - run_start

            # Step 8: Stop monitoring
            resource_samples = monitor.stop()

            # Step 9: Parse YCSB output
            logger.info("  Step 7: Parsing results...")
            parsed_ycsb = parse_ycsb_output(run_output)
            ycsb_metrics = extract_summary(parsed_ycsb)
            resource_summary = compute_resource_summary(resource_samples)

            result = combine_metrics(ycsb_metrics, resource_summary, result)
            result["run_duration_sec"] = run_duration
            result["raw_ycsb_output"] = run_output
            result["resource_samples"] = resource_samples
            result["status"] = "success"

            logger.info(
                f"  Run complete: {ycsb_metrics.get('throughput_ops_sec', 0):.1f} ops/sec, "
                f"Read Avg: {ycsb_metrics.get('read_avg_latency_us', 0):.0f} us"
            )

        except Exception as e:
            logger.error(f"  Run failed: {e}")
            result["status"] = "error"
            result["error"] = str(e)

        # Save raw result
        self._save_raw_result(run_id, result)
        return result

    def run_series(
        self,
        series_name: str,
        db_filter: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Run all configurations in a specific experiment series.

        Args:
            series_name: Name of the series to run (e.g., 'workload', 'concurrency').
            db_filter: Optional database name filter (e.g., 'mongodb').

        Returns:
            List of result dictionaries for all runs.
        """
        if series_name not in self.config.series:
            raise ValueError(
                f"Unknown series '{series_name}'. "
                f"Available: {list(self.config.series.keys())}"
            )

        runs = self.config.series[series_name]
        if db_filter:
            runs = [r for r in runs if r.database.name == db_filter]

        logger.info(f"Running series '{series_name}': {len(runs)} runs")
        results = []

        for i, run_config in enumerate(runs, 1):
            logger.info(f"--- Run {i}/{len(runs)} ---")
            result = self.run_single(run_config)
            results.append(result)

        return results

    def run_all(self, db_filter: Optional[str] = None) -> dict[str, list[dict[str, Any]]]:
        """Run all experiment series.

        Args:
            db_filter: Optional database name filter.

        Returns:
            Dictionary mapping series names to their result lists.
        """
        all_results = {}
        total_runs = sum(len(runs) for runs in self.config.series.values())
        logger.info(f"Running all series: {total_runs} total runs")

        for series_name in self.config.series:
            results = self.run_series(series_name, db_filter)
            all_results[series_name] = results

        return all_results

    def aggregate_series_results(
        self, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Aggregate results across repetitions for the same configuration.

        Groups results by (database, workload, threads, record_count)
        and computes mean/std across repetitions.

        Args:
            results: List of individual run results.

        Returns:
            List of aggregated result dictionaries.
        """
        # Group by configuration key
        groups: dict[str, list[dict[str, Any]]] = {}
        for result in results:
            if result.get("status") != "success":
                continue
            key = (
                f"{result.get('database', '')}_{result.get('workload', '')}_"
                f"t{result.get('threads', 0)}_r{result.get('record_count', 0)}"
            )
            if key not in groups:
                groups[key] = []
            groups[key].append(result)

        aggregated = []
        for key, group_results in groups.items():
            # Filter to only numeric metrics for aggregation
            numeric_results = []
            for r in group_results:
                numeric = {
                    k: v for k, v in r.items()
                    if isinstance(v, (int, float)) and k != "repetition"
                }
                numeric_results.append(numeric)

            agg = aggregate_runs(numeric_results)
            # Add back metadata from first result
            first = group_results[0]
            agg["database"] = first.get("database")
            agg["workload"] = first.get("workload")
            agg["workload_label"] = first.get("workload_label")
            agg["threads"] = first.get("threads")
            agg["record_count"] = first.get("record_count")
            agg["series"] = first.get("series")
            agg["dataset_label"] = first.get("dataset_label")
            agg["num_repetitions"] = len(group_results)
            aggregated.append(agg)

        return aggregated

    def _save_raw_result(self, run_id: str, result: dict[str, Any]) -> None:
        """Save a raw result to a JSON file.

        Args:
            run_id: Unique run identifier for the filename.
            result: Result dictionary to save.
        """
        # Remove non-serializable data
        serializable = {
            k: v for k, v in result.items()
            if k != "resource_samples"  # Samples saved separately if needed
        }

        output_path = self.results_dir / "raw" / f"{run_id}.json"
        try:
            with open(output_path, "w") as f:
                json.dump(serializable, f, indent=2, default=str)
            logger.debug(f"Raw result saved to {output_path}")
        except Exception as e:
            logger.warning(f"Failed to save raw result: {e}")
