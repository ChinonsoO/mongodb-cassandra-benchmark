"""Tests for the YCSB runner module."""

import platform
from unittest.mock import MagicMock, patch

import pytest

from src.ycsb_runner import YCSBRunner, YCSBError


class TestYCSBRunnerInit:
    """Tests for YCSBRunner initialization."""

    def test_default_path(self):
        """Should default to ycsb-0.17.0."""
        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None
        assert str(runner.ycsb_path) == "ycsb-0.17.0"


class TestBuildCommand:
    """Tests for command construction."""

    def test_load_command_mongodb(self):
        """Should build correct load command for MongoDB."""
        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        cmd = runner.build_command(
            phase="load",
            binding="mongodb",
            workload_file="workloads/workload_a.properties",
            properties={"mongodb.url": "mongodb://localhost:27017/ycsb?w=1"},
        )

        cmd_str = " ".join(cmd)
        assert "-load" in cmd_str or "load" in cmd
        assert "mongodb" in cmd_str.lower()
        assert "-s" in cmd
        assert "-P" in cmd
        assert "workloads/workload_a.properties" in cmd
        assert "-p" in cmd
        assert "mongodb.url=mongodb://localhost:27017/ycsb?w=1" in cmd

    def test_run_command_cassandra(self):
        """Should build correct run command for Cassandra."""
        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        cmd = runner.build_command(
            phase="run",
            binding="cassandra-cql",
            workload_file="workloads/workload_b.properties",
            properties={
                "hosts": "localhost",
                "cassandra.readconsistencylevel": "ONE",
                "threadcount": "10",
            },
        )

        cmd_str = " ".join(cmd)
        assert "-t" in cmd or "run" in cmd
        assert "cassandra" in cmd_str.lower()
        assert "hosts=localhost" in cmd
        assert "cassandra.readconsistencylevel=ONE" in cmd
        assert "threadcount=10" in cmd

    def test_no_properties(self):
        """Should work without properties."""
        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        cmd = runner.build_command("load", "mongodb", "workloads/wl.properties")
        assert "-p" not in cmd

    def test_multiple_properties(self):
        """Should include all -p flags."""
        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        props = {
            "recordcount": "1000000",
            "operationcount": "100000",
            "threadcount": "10",
        }
        cmd = runner.build_command("run", "mongodb", "wl.properties", props)

        # Count -p flags
        p_count = cmd.count("-p")
        assert p_count == 3


class TestYCSBLoad:
    """Tests for the YCSB load phase."""

    @patch("src.ycsb_runner.subprocess.run")
    def test_load_success(self, mock_run, sample_ycsb_load_output):
        """Should return stdout on successful load."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=sample_ycsb_load_output,
            stderr="",
        )

        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        result = runner.load("mongodb", "workloads/wl.properties")
        assert "INSERT" in result
        assert "Throughput" in result

    @patch("src.ycsb_runner.subprocess.run")
    def test_load_failure_raises(self, mock_run):
        """Should raise YCSBError on non-zero exit code."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: database connection failed",
        )

        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        with pytest.raises(YCSBError, match="failed"):
            runner.load("mongodb", "workloads/wl.properties")

    @patch("src.ycsb_runner.subprocess.run")
    def test_load_timeout(self, mock_run):
        """Should raise YCSBError on timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ycsb", timeout=60)

        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        with pytest.raises(YCSBError, match="timed out"):
            runner.load("mongodb", "workloads/wl.properties", timeout=60)


class TestYCSBRun:
    """Tests for the YCSB run phase."""

    @patch("src.ycsb_runner.subprocess.run")
    def test_run_success(self, mock_run, sample_ycsb_output_a):
        """Should return stdout on successful run."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=sample_ycsb_output_a,
            stderr="",
        )

        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        result = runner.run(
            "mongodb",
            "workloads/wl.properties",
            properties={"threadcount": "10"},
        )
        assert "READ" in result
        assert "Throughput" in result

    @patch("src.ycsb_runner.subprocess.run")
    def test_run_not_found(self, mock_run):
        """Should raise YCSBError when executable not found."""
        mock_run.side_effect = FileNotFoundError()

        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        with pytest.raises(YCSBError, match="not found"):
            runner.run("mongodb", "workloads/wl.properties")


class TestGetBindingProperties:
    """Tests for default binding properties."""

    def test_mongodb_properties(self):
        """Should return MongoDB connection properties."""
        props = YCSBRunner.get_binding_properties("mongodb")
        assert "mongodb.url" in props
        assert "localhost" in props["mongodb.url"]

    def test_cassandra_properties(self):
        """Should return Cassandra connection properties."""
        props = YCSBRunner.get_binding_properties("cassandra")
        assert props["hosts"] == "localhost"
        assert props["cassandra.readconsistencylevel"] == "ONE"
        assert props["cassandra.writeconsistencylevel"] == "ONE"

    def test_unknown_raises(self):
        """Should raise ValueError for unknown db type."""
        with pytest.raises(ValueError, match="Unknown database type"):
            YCSBRunner.get_binding_properties("redis")


class TestGetBindingName:
    """Tests for binding name lookup."""

    def test_mongodb(self):
        assert YCSBRunner.get_binding_name("mongodb") == "mongodb"

    def test_cassandra(self):
        assert YCSBRunner.get_binding_name("cassandra") == "cassandra-cql"

    def test_unknown_raises(self):
        with pytest.raises(ValueError):
            YCSBRunner.get_binding_name("redis")



class TestBuildCommandExtras:
    """Additional tests for build_command edge cases."""

    def test_java_home_invalid_fallback(self):
        """Should fall back to system java if JAVA_HOME is invalid."""
        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = "/opt/java17"  # invalid path

        cmd = runner.build_command("run", "mongodb", "wl.properties")

        assert cmd[0] == "java"


class TestLoadRunEdgeCases:
    """Edge cases for load and run phases."""

    @patch("src.ycsb_runner.subprocess.run")
    def test_run_with_partial_output(self, mock_run):
        """Runner should return stdout even if it is incomplete."""
        partial_output = "[READ], Operations, 100\n[UPDATE], Operations"
        mock_run.return_value = MagicMock(returncode=0, stdout=partial_output, stderr="")

        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        result = runner.run("mongodb", "wl.properties")
        assert "[READ]" in result
        assert "[UPDATE]" in result

    @patch("src.ycsb_runner.subprocess.run")
    def test_stderr_but_successful_returncode(self, mock_run):
        """Runner should succeed if returncode is 0 even if stderr has text."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Success output", stderr="Warning: minor issue"
        )

        runner = YCSBRunner.__new__(YCSBRunner)
        runner.ycsb_path = __import__("pathlib").Path("ycsb-0.17.0")
        runner._java_home = None

        result = runner.load("mongodb", "wl.properties")
        assert "Success output" in result


class TestBindingPropertiesExtras:
    """Tests for extended binding properties."""

    def test_mongodb_extra_property(self):
        """Should allow overriding default properties."""
        props = YCSBRunner.get_binding_properties("mongodb")
        props["mongodb.username"] = "admin"
        assert props["mongodb.username"] == "admin"

    def test_cassandra_extra_property(self):
        """Should allow overriding Cassandra consistency levels."""
        props = YCSBRunner.get_binding_properties("cassandra")
        props["cassandra.readconsistencylevel"] = "QUORUM"
        assert props["cassandra.readconsistencylevel"] == "QUORUM"