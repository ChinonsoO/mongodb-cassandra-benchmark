"""Main CLI entry point for MongoDB vs Cassandra benchmarks.

Usage:
    python run_benchmarks.py --series all --db all
    python run_benchmarks.py --series workload --db mongodb
    python run_benchmarks.py --series concurrency --db cassandra
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from src.analysis.report import generate_report
from src.analysis.visualizer import generate_all_charts
from src.config import load_experiment_config
from src.db_setup import setup_database
from src.docker_manager import DockerManager, DockerManagerError
from src.experiment_runner import ExperimentRunner
from src.ycsb_runner import YCSBRunner


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="MongoDB vs Cassandra YCSB Benchmark Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_benchmarks.py --series all --db all        Run everything
  python run_benchmarks.py --series workload             Run workload comparison
  python run_benchmarks.py --series concurrency --db mongodb  MongoDB concurrency test
  python run_benchmarks.py --list-series                 Show available series
        """,
    )
    parser.add_argument(
        "--config",
        default="configs/experiment.yaml",
        help="Path to experiment YAML configuration (default: configs/experiment.yaml)",
    )
    parser.add_argument(
        "--series",
        default="all",
        help="Series to run: all, workload, concurrency, dataset_size, bulk_load, stress "
             "(comma-separated for multiple)",
    )
    parser.add_argument(
        "--db",
        default="all",
        choices=["all", "mongodb", "cassandra"],
        help="Database to benchmark (default: all)",
    )
    parser.add_argument(
        "--results-dir",
        default="results",
        help="Output directory for results (default: results/)",
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Skip starting/stopping Docker containers (assume already running)",
    )
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip visualization and report generation after runs",
    )
    parser.add_argument(
        "--list-series",
        action="store_true",
        help="List available experiment series and exit",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    parser.add_argument(
        "--java-home",
        default=None,
        help="Path to Java installation (overrides JAVA_HOME and config)",
    )
    return parser.parse_args()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the benchmark suite."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    """Main benchmark execution workflow.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    args = parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    # Load configuration
    try:
        config = load_experiment_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Configuration error: {e}")
        return 1

    # List series and exit if requested
    if args.list_series:
        print("\nAvailable experiment series:")
        for name, runs in config.series.items():
            print(f"  {name}: {len(runs)} runs")
        total = sum(len(r) for r in config.series.values())
        print(f"\nTotal: {total} runs")
        return 0

    # Determine which series to run
    if args.series == "all":
        series_to_run = list(config.series.keys())
    else:
        series_to_run = [s.strip() for s in args.series.split(",")]
        for s in series_to_run:
            if s not in config.series:
                logger.error(
                    f"Unknown series '{s}'. Available: {list(config.series.keys())}"
                )
                return 1

    # Database filter
    db_filter = None if args.db == "all" else args.db

    # Initialize components
    docker_manager = DockerManager()
    java_home = args.java_home or config.java_home or None
    ycsb_runner = YCSBRunner(config.ycsb_path, java_home=java_home)

    logger.info("=" * 60)
    logger.info("  MongoDB vs Cassandra Benchmark Suite")
    logger.info("=" * 60)
    logger.info(f"Series: {', '.join(series_to_run)}")
    logger.info(f"Database: {args.db}")
    logger.info(f"Results directory: {args.results_dir}")

    # Start Docker containers
    if not args.skip_docker:
        try:
            docker_manager.start_containers()

            # Wait for databases to be ready
            databases_to_check = (
                [db_filter] if db_filter
                else list(config.databases.keys())
            )
            for db_name in databases_to_check:
                db_config = config.databases[db_name]
                docker_manager.wait_for_ready(db_config.host, db_config.port)

            # Set up schemas
            for db_name in databases_to_check:
                db_config = config.databases[db_name]
                setup_database(db_config.name, db_config.host, db_config.port)

        except (DockerManagerError, RuntimeError) as e:
            logger.error(f"Docker setup failed: {e}")
            return 1

    # Run experiments
    runner = ExperimentRunner(
        config=config,
        docker_manager=docker_manager,
        ycsb_runner=ycsb_runner,
        results_dir=args.results_dir,
    )

    all_results = {}
    all_raw_results = {}
    analysis_dir = str(Path(args.results_dir) / "analysis")
    start_time = time.time()

    for series_name in series_to_run:
        try:
            logger.info(f"\n{'='*40}")
            logger.info(f"  Starting series: {series_name}")
            logger.info(f"{'='*40}")
            results = runner.run_series(series_name, db_filter)
            all_raw_results[series_name] = results
            aggregated = runner.aggregate_series_results(results)
            all_results[series_name] = aggregated
        except Exception as e:
            logger.error(f"Series '{series_name}' failed: {e}")
            all_raw_results[series_name] = []
            all_results[series_name] = []

        # Save analysis incrementally after each series so partial
        # results survive if a later series crashes.
        if not args.skip_analysis and all_results.get(series_name):
            try:
                generate_all_charts(all_results, analysis_dir, raw_results=all_raw_results)
            except Exception as e:
                logger.warning(f"Chart generation failed after {series_name}: {e}")
            try:
                generate_report(all_results, analysis_dir, raw_results=all_raw_results)
            except Exception as e:
                logger.warning(f"Report generation failed after {series_name}: {e}")

    total_time = time.time() - start_time
    logger.info(f"\nAll series completed in {total_time:.1f}s")

    # Final analysis pass with all results combined
    if not args.skip_analysis and any(all_results.values()):
        logger.info("\nGenerating final analysis...")
        try:
            generate_all_charts(all_results, analysis_dir, raw_results=all_raw_results)
        except Exception as e:
            logger.warning(f"Chart generation failed: {e}")

        try:
            report = generate_report(all_results, analysis_dir, raw_results=all_raw_results)
            print(report)
        except Exception as e:
            logger.warning(f"Report generation failed: {e}")

    # Stop Docker containers
    if not args.skip_docker:
        try:
            docker_manager.stop_containers()
        except DockerManagerError as e:
            logger.warning(f"Failed to stop containers: {e}")

    logger.info("Benchmark suite complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
