"""Tests for the Docker manager module."""

import socket
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.docker_manager import DockerManager, DockerManagerError


class TestDockerManagerInit:
    """Tests for DockerManager initialization."""

    def test_default_compose_file(self):
        """Should use docker-compose.yml by default."""
        dm = DockerManager()
        assert str(dm.compose_file) == "docker-compose.yml"

    def test_custom_compose_file(self, tmp_path):
        """Should accept a custom compose file path."""
        compose = tmp_path / "custom-compose.yml"
        compose.touch()
        dm = DockerManager(compose_file=str(compose))
        assert dm.compose_file == compose


class TestStartContainers:
    """Tests for starting Docker containers."""

    @patch("src.docker_manager.subprocess.run")
    def test_start_calls_compose_up(self, mock_run):
        """Should call docker compose up -d."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        dm = DockerManager()
        dm.start_containers()

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "docker" in args
        assert "compose" in args
        assert "up" in args
        assert "-d" in args

    @patch("src.docker_manager.subprocess.run")
    def test_start_failure_raises(self, mock_run):
        """Should raise DockerManagerError on failure."""
        mock_run.return_value = MagicMock(
            returncode=1, stderr="Error: service not found"
        )
        dm = DockerManager()
        with pytest.raises(DockerManagerError, match="failed"):
            dm.start_containers()


class TestStopContainers:
    """Tests for stopping Docker containers."""

    @patch("src.docker_manager.subprocess.run")
    def test_stop_calls_compose_down(self, mock_run):
        """Should call docker compose down."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        dm = DockerManager()
        dm.stop_containers()

        args = mock_run.call_args[0][0]
        assert "down" in args

    @patch("src.docker_manager.subprocess.run")
    def test_stop_with_volumes(self, mock_run):
        """Should pass -v flag when remove_volumes=True."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        dm = DockerManager()
        dm.stop_containers(remove_volumes=True)

        args = mock_run.call_args[0][0]
        assert "-v" in args


class TestWaitForReady:
    """Tests for the wait_for_ready port check."""

    @patch("src.docker_manager.DockerManager._check_port")
    def test_immediate_ready(self, mock_check):
        """Should return True immediately if port is ready."""
        mock_check.return_value = True
        dm = DockerManager()
        result = dm.wait_for_ready("localhost", 27017, timeout=5)
        assert result is True

    @patch("src.docker_manager.time.sleep")
    @patch("src.docker_manager.DockerManager._check_port")
    def test_ready_after_retries(self, mock_check, mock_sleep):
        """Should retry and succeed after initial failures."""
        mock_check.side_effect = [False, False, True]
        dm = DockerManager()
        result = dm.wait_for_ready("localhost", 27017, timeout=30, interval=0.1)
        assert result is True
        assert mock_check.call_count == 3

    @patch("src.docker_manager.time.time")
    @patch("src.docker_manager.time.sleep")
    @patch("src.docker_manager.DockerManager._check_port")
    def test_timeout_raises(self, mock_check, mock_sleep, mock_time):
        """Should raise DockerManagerError on timeout."""
        mock_check.return_value = False
        # Simulate time progressing past timeout
        mock_time.side_effect = [0, 5, 10, 15, 130]

        dm = DockerManager()
        with pytest.raises(DockerManagerError, match="Timeout"):
            dm.wait_for_ready("localhost", 27017, timeout=120, interval=0.1)


class TestCheckPort:
    """Tests for the static _check_port method."""

    @patch("src.docker_manager.socket.create_connection")
    def test_port_open(self, mock_conn):
        """Should return True when connection succeeds."""
        mock_conn.return_value.__enter__ = MagicMock()
        mock_conn.return_value.__exit__ = MagicMock(return_value=False)
        assert DockerManager._check_port("localhost", 27017) is True

    @patch("src.docker_manager.socket.create_connection")
    def test_port_closed(self, mock_conn):
        """Should return False when connection is refused."""
        mock_conn.side_effect = ConnectionRefusedError()
        assert DockerManager._check_port("localhost", 27017) is False

    @patch("src.docker_manager.socket.create_connection")
    def test_port_timeout(self, mock_conn):
        """Should return False on timeout."""
        mock_conn.side_effect = TimeoutError()
        assert DockerManager._check_port("localhost", 27017) is False


class TestGetContainerStats:
    """Tests for container stats retrieval."""

    def test_get_container_stats(self, sample_docker_stats):
        """Should return stats from the Docker API."""
        mock_container = MagicMock()
        mock_container.stats.return_value = sample_docker_stats

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        dm = DockerManager()
        dm._client = mock_client

        stats = dm.get_container_stats("ycsb-mongodb")
        assert stats == sample_docker_stats

    def test_container_not_found(self):
        """Should raise DockerManagerError for missing container."""
        import docker

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = docker.errors.NotFound("not found")

        dm = DockerManager()
        dm._client = mock_client

        with pytest.raises(DockerManagerError, match="not found"):
            dm.get_container("nonexistent")


class TestIsContainerRunning:
    """Tests for container status check."""

    def test_running_container(self):
        """Should return True for running container."""
        mock_container = MagicMock()
        mock_container.status = "running"

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        dm = DockerManager()
        dm._client = mock_client

        assert dm.is_container_running("ycsb-mongodb") is True

    def test_stopped_container(self):
        """Should return False for stopped container."""
        mock_container = MagicMock()
        mock_container.status = "exited"

        mock_client = MagicMock()
        mock_client.containers.get.return_value = mock_container

        dm = DockerManager()
        dm._client = mock_client

        assert dm.is_container_running("ycsb-mongodb") is False

    def test_nonexistent_container(self):
        """Should return False for container that doesn't exist."""
        import docker

        mock_client = MagicMock()
        mock_client.containers.get.side_effect = docker.errors.NotFound("nope")

        dm = DockerManager()
        dm._client = mock_client

        assert dm.is_container_running("nonexistent") is False
