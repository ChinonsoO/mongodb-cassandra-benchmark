# MongoDB vs Cassandra Performance Benchmark

A benchmarking suite that compares **MongoDB 7.0** and **Cassandra 4.1** under controlled [YCSB](https://github.com/brianfrankcooper/YCSB) workloads. It measures throughput (ops/sec), latency (average, P95, P99), and resource utilization (CPU, memory, disk I/O, network) across different workload patterns, concurrency levels, and dataset sizes.

## Team Members (SENG 533)

- Aly Farouz (30169931)
- Jung-Hwan Park (30146353)
- Chinonso Oragwam (30142426)
- Jinsu Kwak (30097737)

---

## What This Project Does

1. **Spins up** MongoDB and Cassandra in Docker containers with fixed CPU quotas/pinning and memory limits.
2. **Loads** data into each database using YCSB (a standard NoSQL benchmarking tool).
3. **Runs** configurable experiment series — varying workloads, thread counts, and dataset sizes.
4. **Monitors** container-level resource usage (normalized CPU %, memory, block I/O, network) in a background thread while each benchmark runs.
5. **Parses** YCSB output to extract throughput and latency metrics.
6. **Aggregates** results across multiple repetitions (mean ± std dev).
7. **Generates** comparison charts (bar charts, line graphs, time-series) and summary reports (text tables, CSV files).

### Experiment Series

| Series | What It Tests | Configurations |
|--------|---------------|----------------|
| **Workload** | Workloads A (update heavy), B (read heavy), F (read-modify-write) at baseline | 3 workloads |
| **Concurrency** | Workload A at 1, 10, 50, 100 threads | 4 thread levels |
| **Dataset Size** | Workload A at 100 MB, 1 GB, 10 GB | 3 sizes |
| **Bulk Load** | 100% insert workload at 1 GB | 1 config |
| **Stress** | Workload A ramping from 1 → 100 threads | 6 thread levels |

Each configuration is run against **both databases**, repeated **3 times** = **102 total runs**.

---

## Prerequisites

Before you begin, make sure you have the following installed:

| Requirement | Version | Purpose |
|-------------|---------|---------|
| **Python** | 3.11+ | Orchestration, analysis, testing |
| **Docker Desktop** | Latest | Run MongoDB & Cassandra containers |
| **Docker Compose** | v2 (bundled with Docker Desktop) | Multi-container management |
| **Java** | 8 or 11 | Required by YCSB (the benchmarking tool) |
| **Git** | Any | Version control |
| **Disk Space** | ~25–30 GB free | Database data (up to 10 GB per DB), YCSB (~1.5 GB), Docker images (~1.2 GB), venv (~500 MB) |

> **Windows users:** Make sure Docker Desktop is running before starting. Java must be on your `PATH` or `JAVA_HOME` must be set (verify with `java -version`). See [Configuring Java](#configuring-java) if you have trouble.
>
> **Disk space note:** The largest dataset (10 GB) requires the most space. Databases are reset between runs, so peak usage is one database holding the largest dataset at a time — not all datasets stacked. You can reduce the `large` dataset size in `configs/experiment.yaml` or skip the `dataset_size` series to lower requirements.

---

## Step-by-Step Setup

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd mongodb-cassandra-benchmark
```

### Step 2: Activate the Virtual Environment

The project includes a Python virtual environment (`venv/`).

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
source venv/bin/activate
```

You should see `(venv)` in your terminal prompt.

### Step 3: Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs: `docker`, `pyyaml`, `pandas`, `numpy`, `matplotlib`, `seaborn`, `cassandra-driver`, `pymongo`, `tabulate`, `scipy`, `pytest`, `pytest-mock`.

### Step 4: Download YCSB

```bash
python setup_ycsb.py
```

This script will:
- Verify Java is installed
- Download YCSB 0.17.0 (~675 MB) from GitHub releases
- Extract it to `ycsb-0.17.0/` in the project directory

> If the download is slow, you can manually download from [YCSB releases](https://github.com/brianfrankcooper/YCSB/releases/tag/0.17.0) and extract the tarball here.

### Step 5: Start the Database Containers

```bash
docker compose up -d
```

This launches two containers:

| Container | Image | Port | CPU Limit | CPU Pinning | Memory Limit |
|-----------|-------|------|-----------|-------------|-------------|
| `ycsb-mongodb` | `mongo:7.0` | 27017 | 2.0 CPUs | `0-1` | 2 GB |
| `ycsb-cassandra` | `cassandra:4.1` | 9042 | 2.0 CPUs | `0-1` | 2 GB |

Verify they are running:
```bash
docker compose ps
```

> **Note:** Cassandra takes 30–60 seconds to fully initialize. The benchmark script automatically waits for readiness before starting tests.

---

## Running Benchmarks

### Run All Experiments

```bash
python run_benchmarks.py
```

This runs every series against both databases with the default configuration.

### Run a Specific Series

```bash
python run_benchmarks.py --series workload
python run_benchmarks.py --series concurrency
python run_benchmarks.py --series dataset_size
python run_benchmarks.py --series bulk_load
python run_benchmarks.py --series stress
```

### Run Multiple Series

```bash
python run_benchmarks.py --series workload,concurrency
```

### Run Against a Single Database

```bash
python run_benchmarks.py --series workload --db mongodb
python run_benchmarks.py --series concurrency --db cassandra
```

### List All Available Series

```bash
python run_benchmarks.py --list-series
```

### Configuring Java

YCSB requires a Java runtime. The benchmark script looks for Java in this order:

1. **`--java-home` CLI flag** — highest priority, overrides everything else.
2. **`java_home` in `configs/experiment.yaml`** — set once for the project.
3. **`JAVA_HOME` environment variable** — standard system-wide setting.
4. **System `PATH`** — if `java` is already on your PATH, no configuration is needed.

If Java is not found by any of these methods, the script will print an error listing all four options.

**Option A — CLI flag (one-off):**
```bash
python run_benchmarks.py --java-home "C:\Program Files\Java\jdk-17"
```

**Option B — Config file (persistent):**

Edit `configs/experiment.yaml` and uncomment the `java_home` line under `ycsb:`:
```yaml
ycsb:
  path: ycsb-0.17.0
  java_home: C:\Program Files\Java\jdk-17   # <-- set your path here
```

**Option C — Environment variable:**

```powershell
# Windows (PowerShell)
$env:JAVA_HOME = "C:\Program Files\Java\jdk-17"

# macOS / Linux
export JAVA_HOME=/usr/lib/jvm/java-17
```

### Skip Docker Management

If you already started the containers manually:
```bash
python run_benchmarks.py --skip-docker
```

### Skip Report/Chart Generation

If you only want the raw data:
```bash
python run_benchmarks.py --skip-analysis
```

### Enable Verbose Logging

```bash
python run_benchmarks.py -v
```

### Full Option Reference

```
python run_benchmarks.py --help

Options:
  --config PATH         Path to experiment YAML config (default: configs/experiment.yaml)
  --series NAME         Series to run: all, workload, concurrency, dataset_size,
                        bulk_load, stress (comma-separated)
  --db {all,mongodb,cassandra}
                        Database to benchmark (default: all)
  --results-dir DIR     Output directory (default: results/)
  --skip-docker         Don't start/stop Docker containers
  --skip-analysis       Don't generate charts and reports
  --list-series         Show available series and exit
  --java-home PATH      Path to Java installation (overrides JAVA_HOME and config)
  -v, --verbose         DEBUG-level logging
```

---

## Understanding the Output

After a benchmark run completes, results are saved to `results/`:

```
results/
├── raw/                          # Raw JSON for every individual run
│   ├── mongodb_workload_a_t10_r1000000_rep1.json
│   ├── mongodb_workload_a_t10_r1000000_rep2.json
│   ├── cassandra_workload_a_t10_r1000000_rep1.json
│   └── ...
└── analysis/                     # Aggregated analysis outputs
    ├── summary_report.txt        # Text summary table + environment summary
    ├── all_results.csv           # Combined CSV of all results
    ├── workload_results.csv      # Per-series CSV
    ├── concurrency_results.csv
    ├── throughput_comparison.png  # Bar chart: throughput by workload
    ├── latency_comparison.png    # 3-panel latency percentiles
    ├── throughput_vs_threads.png  # Line chart: scaling with threads
    ├── latency_vs_threads.png    # Latency at different concurrencies
    ├── dataset_scaling.png       # Performance vs dataset size
    └── resource_*.png            # CPU/memory/IO time-series charts
```

### Key Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| `throughput_ops_sec` | ops/sec | Total operations per second |
| `read_avg_latency_us` | μs | Average read latency |
| `read_p95_latency_us` | μs | 95th percentile read latency |
| `read_p99_latency_us` | μs | 99th percentile read latency |
| `update_avg_latency_us` | μs | Average update latency |
| `avg_cpu_percent` | % | Average CPU utilization during run, normalized to the container's allowed CPU budget|
| `max_mem_usage_mb` | MB | Peak memory usage |
| `total_blk_read_mb` | MB | Total disk reads |
| `total_net_rx_mb` | MB | Total network received |

---

## Customizing Experiments

All experiment parameters live in `configs/experiment.yaml`. You can modify:

- **Database connection settings** — hosts, ports, YCSB binding properties
- **Dataset sizes** — add/change the small/medium/large definitions
- **Baseline** — default thread count, dataset, operation count
- **Repetitions** — how many times each configuration is repeated (default: 3)
- **Series** — add new series, change thread levels, workloads, etc.

### YCSB Workload Files

YCSB workload definitions are in the `workloads/` directory:

| File | Pattern | Description |
|------|---------|-------------|
| `workload_a.properties` | 50% read / 50% update | Update-heavy |
| `workload_b.properties` | 95% read / 5% update | Read-mostly |
| `workload_f.properties` | 50% read / 50% read-modify-write | Read-modify-write |
| `workload_bulk.properties` | 100% insert | Bulk data loading |
| `workload_stress.properties` | 50% read / 50% update | Stress testing (same as A) |

Each record is ~1 KB (10 fields × 100 bytes), using Zipfian distribution.

---

## Running Tests

The project includes 160 unit tests that use mocked dependencies — **no Docker or databases needed**.

```bash
python -m pytest tests/ -v
```

Run a specific test file:
```bash
python -m pytest tests/test_config.py -v
python -m pytest tests/test_ycsb_parser.py -v
```

Run with short summary:
```bash
python -m pytest tests/ --tb=short
```

### Test Coverage by Module

| Test File | Module Tested | Tests |
|-----------|--------------|-------|
| `test_config.py` | Configuration loading, dataclasses | 13 |
| `test_ycsb_parser.py` | YCSB output parsing | 15 |
| `test_metrics.py` | Statistical aggregation, formatting | 19 |
| `test_docker_manager.py` | Docker container management | 15 |
| `test_db_setup.py` | Database schema setup/reset | 14 |
| `test_ycsb_runner.py` | YCSB command building/execution | 14 |
| `test_resource_monitor.py` | Container resource monitoring | 14 |
| `test_experiment_runner.py` | Experiment orchestration | 8 |
| `test_visualizer.py` | Chart generation | 12 |
| `test_report.py` | Reports/CSV/saturation analysis | 16 |

---

## Project Structure

```
mongodb-cassandra-benchmark/
│
├── run_benchmarks.py            # Main CLI entry point
├── setup_ycsb.py                # Downloads & installs YCSB 0.17.0
├── docker-compose.yml           # MongoDB 7.0 & Cassandra 4.1 containers
├── requirements.txt             # Python dependencies
│
├── configs/
│   └── experiment.yaml          # All experiment parameters & series definitions
│
├── workloads/                   # YCSB workload property files
│   ├── workload_a.properties    # 50/50 read/update
│   ├── workload_b.properties    # 95/5 read/update
│   ├── workload_f.properties    # Read-modify-write
│   ├── workload_bulk.properties # 100% inserts
│   └── workload_stress.properties
│
├── src/                         # Source code
│   ├── config.py                # YAML config → dataclasses
│   ├── docker_manager.py        # Start/stop containers, health checks
│   ├── db_setup.py              # Create keyspace/tables, reset data
│   ├── ycsb_runner.py           # Build & execute YCSB commands
│   ├── ycsb_parser.py           # Parse YCSB text output → dicts
│   ├── resource_monitor.py      # Background Docker stats collection
│   ├── metrics.py               # Aggregate runs, compute summaries
│   ├── experiment_runner.py     # Orchestrates the full workflow
│   └── analysis/
│       ├── visualizer.py        # matplotlib/seaborn chart generation
│       └── report.py            # Text tables, CSV export, saturation detection
│
├── tests/                       # 160 unit tests (mocked, no Docker needed)
│   ├── conftest.py              # Shared fixtures & sample data
│   ├── test_config.py
│   ├── test_ycsb_parser.py
│   ├── test_metrics.py
│   ├── test_docker_manager.py
│   ├── test_db_setup.py
│   ├── test_ycsb_runner.py
│   ├── test_resource_monitor.py
│   ├── test_experiment_runner.py
│   ├── test_visualizer.py
│   └── test_report.py
│
├── results/                     # Benchmark output (gitignored)
│   ├── raw/                     # Per-run JSON files
│   └── analysis/                # Charts, CSVs, reports
│
└── venv/                        # Python virtual environment
```

---

## How It Works (Architecture)

The benchmark pipeline for each individual run follows this sequence:

```
1. Reset database       →  Clear previous data (truncate/drop)
2. Setup schema         →  Create keyspace & table (Cassandra) or verify connection (MongoDB)
3. Load data (YCSB)     →  Insert the target number of records
4. Warmup (YCSB)        →  Short run to warm caches
5. Start resource monitor →  Background thread polling Docker stats
6. Run workload (YCSB)  →  Execute the actual benchmark
7. Stop resource monitor →  Collect all resource samples
8. Parse YCSB output    →  Extract throughput & latency metrics
9. Save raw results     →  Write JSON to results/raw/ with environment metadata
```

After all runs in a series complete:
- Results are grouped by configuration and aggregated (mean ± std dev)
- Charts and reports are generated from the aggregated data

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `java` not found | Install Java 8 or 11 and add to PATH |
| Docker containers won't start | Ensure Docker Desktop is running |
| Cassandra timeout on startup | Increase timeout — Cassandra needs 30-60s to initialize |
| `cassandra.DependencyException` in tests | This is a Python 3.12 compatibility issue with the driver — tests use `sys.modules` patching to avoid it |
| YCSB download is slow | Manually download from [GitHub releases](https://github.com/brianfrankcooper/YCSB/releases/tag/0.17.0) and extract to `ycsb-0.17.0/` |
| Permission denied on Windows | Run terminal as Administrator, or check Docker Desktop sharing settings |

---

## Quick Reference

```bash
# Setup (one-time)
.\venv\Scripts\Activate.ps1          # Activate venv (Windows PowerShell)
pip install -r requirements.txt      # Install dependencies
python setup_ycsb.py                 # Download YCSB
docker compose up -d                 # Start databases

# Run benchmarks
python run_benchmarks.py                              # Run all
python run_benchmarks.py --series workload --db mongodb  # Specific series + DB
python run_benchmarks.py --list-series                # See what's available

# Tests
python -m pytest tests/ -v           # Run all 160 tests

# Cleanup
docker compose down -v               # Stop containers & remove data volumes
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## YCSB Workloads

- **Workload A** (Update Heavy): 50% reads, 50% updates
- **Workload B** (Read Heavy): 95% reads, 5% updates
- **Workload F** (Read-Modify-Write): 50% reads, 50% RMW
- **Bulk Load**: 100% inserts
- **Stress Test**: Workload A with increasing concurrency
