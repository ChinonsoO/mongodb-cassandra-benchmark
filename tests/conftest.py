"""Shared test fixtures for the benchmark test suite."""

import pytest


# ============================================================
# Sample YCSB output fixtures
# ============================================================

SAMPLE_YCSB_WORKLOAD_A_OUTPUT = """\
[OVERALL], RunTime(ms), 10110
[OVERALL], Throughput(ops/sec), 9891.196834817013
[TOTAL_GCS_Copy], Count, 5
[TOTAL_GC_TIME_Copy], Time(ms), 30
[TOTAL_GCS_MarkSweepCompact], Count, 0
[TOTAL_GC_TIME_MarkSweepCompact], Time(ms), 0
[TOTAL_GC_TIME], Time(ms), 30
[READ], Operations, 5091
[READ], AverageLatency(us), 383.24
[READ], MinLatency(us), 42
[READ], MaxLatency(us), 230000
[READ], 95thPercentileLatency(us), 1200
[READ], 99thPercentileLatency(us), 3500
[READ], Return=OK, 5091
[UPDATE], Operations, 4909
[UPDATE], AverageLatency(us), 549.8
[UPDATE], MinLatency(us), 58
[UPDATE], MaxLatency(us), 195000
[UPDATE], 95thPercentileLatency(us), 1500
[UPDATE], 99thPercentileLatency(us), 4200
[UPDATE], Return=OK, 4909
[CLEANUP], Operations, 10
[CLEANUP], AverageLatency(us), 500.0
"""

SAMPLE_YCSB_WORKLOAD_B_OUTPUT = """\
[OVERALL], RunTime(ms), 8523
[OVERALL], Throughput(ops/sec), 11732.65
[READ], Operations, 9505
[READ], AverageLatency(us), 210.5
[READ], MinLatency(us), 35
[READ], MaxLatency(us), 150000
[READ], 95thPercentileLatency(us), 800
[READ], 99thPercentileLatency(us), 2100
[READ], Return=OK, 9505
[UPDATE], Operations, 495
[UPDATE], AverageLatency(us), 620.3
[UPDATE], MinLatency(us), 72
[UPDATE], MaxLatency(us), 85000
[UPDATE], 95thPercentileLatency(us), 1800
[UPDATE], 99thPercentileLatency(us), 5000
[UPDATE], Return=OK, 495
[CLEANUP], Operations, 10
[CLEANUP], AverageLatency(us), 450.0
"""

SAMPLE_YCSB_WORKLOAD_F_OUTPUT = """\
[OVERALL], RunTime(ms), 12500
[OVERALL], Throughput(ops/sec), 8000.0
[READ], Operations, 5000
[READ], AverageLatency(us), 450.0
[READ], MinLatency(us), 55
[READ], MaxLatency(us), 280000
[READ], 95thPercentileLatency(us), 1500
[READ], 99thPercentileLatency(us), 4800
[READ], Return=OK, 5000
[READ-MODIFY-WRITE], Operations, 5000
[READ-MODIFY-WRITE], AverageLatency(us), 1200.0
[READ-MODIFY-WRITE], 95thPercentileLatency(us), 3500
[READ-MODIFY-WRITE], 99thPercentileLatency(us), 8500
[UPDATE], Operations, 5000
[UPDATE], AverageLatency(us), 600.0
[UPDATE], MinLatency(us), 65
[UPDATE], MaxLatency(us), 210000
[UPDATE], 95thPercentileLatency(us), 1600
[UPDATE], 99thPercentileLatency(us), 4500
[UPDATE], Return=OK, 5000
[CLEANUP], Operations, 10
[CLEANUP], AverageLatency(us), 510.0
"""

SAMPLE_YCSB_LOAD_OUTPUT = """\
[OVERALL], RunTime(ms), 25000
[OVERALL], Throughput(ops/sec), 40000.0
[INSERT], Operations, 1000000
[INSERT], AverageLatency(us), 230.0
[INSERT], MinLatency(us), 30
[INSERT], MaxLatency(us), 500000
[INSERT], 95thPercentileLatency(us), 800
[INSERT], 99thPercentileLatency(us), 2000
[INSERT], Return=OK, 1000000
[CLEANUP], Operations, 10
[CLEANUP], AverageLatency(us), 250.0
"""


@pytest.fixture
def sample_ycsb_output_a():
    """Realistic YCSB Workload A output."""
    return SAMPLE_YCSB_WORKLOAD_A_OUTPUT


@pytest.fixture
def sample_ycsb_output_b():
    """Realistic YCSB Workload B output."""
    return SAMPLE_YCSB_WORKLOAD_B_OUTPUT


@pytest.fixture
def sample_ycsb_output_f():
    """Realistic YCSB Workload F output."""
    return SAMPLE_YCSB_WORKLOAD_F_OUTPUT


@pytest.fixture
def sample_ycsb_load_output():
    """Realistic YCSB load phase output."""
    return SAMPLE_YCSB_LOAD_OUTPUT


# ============================================================
# Sample Docker stats fixtures
# ============================================================

SAMPLE_DOCKER_STATS = {
    "cpu_stats": {
        "cpu_usage": {
            "total_usage": 500000000,
            "percpu_usage": [250000000, 250000000],
        },
        "system_cpu_usage": 10000000000,
        "online_cpus": 4,
    },
    "precpu_stats": {
        "cpu_usage": {
            "total_usage": 400000000,
            "percpu_usage": [200000000, 200000000],
        },
        "system_cpu_usage": 9000000000,
    },
    "memory_stats": {
        "usage": 256 * 1024 * 1024,  # 256 MB
        "limit": 2048 * 1024 * 1024,  # 2 GB
    },
    "blkio_stats": {
        "io_service_bytes_recursive": [
            {"op": "read", "value": 50 * 1024 * 1024},
            {"op": "write", "value": 30 * 1024 * 1024},
        ],
    },
    "networks": {
        "eth0": {
            "rx_bytes": 5 * 1024 * 1024,
            "tx_bytes": 2 * 1024 * 1024,
        },
    },
}


@pytest.fixture
def sample_docker_stats():
    """Sample Docker container stats."""
    return dict(SAMPLE_DOCKER_STATS)


# ============================================================
# Sample config fixtures
# ============================================================

SAMPLE_EXPERIMENT_YAML = """\
databases:
  mongodb:
    host: localhost
    port: 27017
    container_name: ycsb-mongodb
    ycsb_binding: mongodb
    connection_properties:
      mongodb.url: "mongodb://localhost:27017/ycsb?w=1"
  cassandra:
    host: localhost
    port: 9042
    container_name: ycsb-cassandra
    ycsb_binding: cassandra-cql
    connection_properties:
      hosts: localhost
      cassandra.readconsistencylevel: ONE
      cassandra.writeconsistencylevel: ONE

ycsb:
  path: ycsb-0.17.0
  bytes_per_record: 1000

dataset_sizes:
  small:
    label: "100 MB"
    size_mb: 100
    record_count: 100000
  medium:
    label: "1 GB"
    size_mb: 1024
    record_count: 1000000

baseline:
  dataset: medium
  threads: 10
  operation_count: 100000
  warmup_operation_count: 1000

repetitions: 2

series:
  workload:
    description: "Workload comparison"
    workloads:
      - name: workload_a
        file: workloads/workload_a.properties
        label: "Workload A"
      - name: workload_b
        file: workloads/workload_b.properties
        label: "Workload B"
    dataset: medium
    threads: 10
    operation_count: 10000

  concurrency:
    description: "Concurrency series"
    workloads:
      - name: workload_a
        file: workloads/workload_a.properties
        label: "Workload A"
    dataset: medium
    thread_levels: [1, 10, 50]
    operation_count: 10000
"""


@pytest.fixture
def sample_experiment_yaml(tmp_path):
    """Create a temporary experiment YAML config file."""
    config_path = tmp_path / "experiment.yaml"
    config_path.write_text(SAMPLE_EXPERIMENT_YAML)
    return str(config_path)


@pytest.fixture
def tmp_results_dir(tmp_path):
    """Temporary results directory."""
    results = tmp_path / "results"
    results.mkdir()
    (results / "raw").mkdir()
    (results / "analysis").mkdir()
    return str(results)
