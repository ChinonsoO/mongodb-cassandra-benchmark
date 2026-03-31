"""Tests for benchmark environment metadata capture."""

from unittest.mock import MagicMock, patch

from src.environment import collect_environment_snapshot


class TestCollectEnvironmentSnapshot:
    """Tests for host/runtime environment snapshots."""

    @patch("src.environment._safe_command_output")
    @patch("src.environment.socket.gethostname")
    @patch("src.environment.platform.processor")
    @patch("src.environment.platform.machine")
    @patch("src.environment.platform.version")
    @patch("src.environment.platform.release")
    @patch("src.environment.platform.system")
    @patch("src.environment.os.cpu_count")
    def test_collects_host_runtime_and_container_metadata(
        self,
        mock_cpu_count,
        mock_system,
        mock_release,
        mock_version,
        mock_machine,
        mock_processor,
        mock_hostname,
        mock_command_output,
    ):
        mock_cpu_count.return_value = 8
        mock_system.return_value = "Windows"
        mock_release.return_value = "11"
        mock_version.return_value = "10.0.26100"
        mock_machine.return_value = "AMD64"
        mock_processor.return_value = "Intel64 Family"
        mock_hostname.return_value = "bench-host"
        mock_command_output.return_value = 'openjdk version "21.0.2"'

        mock_container = MagicMock()
        mock_container.attrs = {
            "Name": "/ycsb-mongodb",
            "Config": {"Image": "mongo:7.0"},
            "HostConfig": {
                "NanoCpus": 2_000_000_000,
                "CpusetCpus": "0-1",
                "Memory": 2 * 1024 * 1024 * 1024,
            },
        }

        mock_client = MagicMock()
        mock_client.version.return_value = {"Version": "28.0.1"}
        mock_client.info.return_value = {
            "OperatingSystem": "Docker Desktop",
            "Architecture": "x86_64",
            "NCPU": 8,
            "MemTotal": 16 * 1024 * 1024 * 1024,
            "Driver": "overlay2",
        }

        docker_manager = MagicMock()
        docker_manager.client = mock_client
        docker_manager.get_container.return_value = mock_container

        ycsb_runner = MagicMock()
        ycsb_runner.ycsb_path = "ycsb-0.17.0"
        ycsb_runner._get_java_executable.return_value = "java"

        snapshot = collect_environment_snapshot(
            docker_manager=docker_manager,
            ycsb_runner=ycsb_runner,
            container_name="ycsb-mongodb",
        )

        assert snapshot["host"]["hostname"] == "bench-host"
        assert snapshot["host"]["logical_cpus"] == 8
        assert snapshot["runtime"]["java_version"] == 'openjdk version "21.0.2"'
        assert snapshot["docker"]["server_version"] == "28.0.1"
        assert snapshot["target_container"]["name"] == "ycsb-mongodb"
        assert snapshot["target_container"]["cpus"] == 2.0
        assert snapshot["target_container"]["cpuset_cpus"] == "0-1"
        assert snapshot["target_container"]["memory_limit_mb"] == 2048.0

    def test_handles_missing_docker_metadata(self):
        ycsb_runner = MagicMock()
        ycsb_runner.ycsb_path = "ycsb-0.17.0"
        ycsb_runner._get_java_executable.side_effect = RuntimeError("no java")

        snapshot = collect_environment_snapshot(
            docker_manager=None,
            ycsb_runner=ycsb_runner,
            container_name="",
        )

        assert snapshot["docker"] == {}
        assert snapshot["target_container"] == {}
