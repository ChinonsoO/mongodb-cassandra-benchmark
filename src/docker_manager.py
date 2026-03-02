"""Docker container lifecycle management for benchmark databases."""

import logging
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

import docker

logger = logging.getLogger(__name__)


class DockerManagerError(Exception):
    """Raised when a Docker operation fails."""


class DockerManager:
    """Manage Docker containers for MongoDB and Cassandra benchmarks.

    Handles starting, stopping, health checking, and resetting
    database containers via Docker Compose and the Docker SDK.
    """

    def __init__(
        self,
        compose_file: str = "docker-compose.yml",
        project_dir: str | None = None,
    ):
        """Initialize DockerManager.

        Args:
            compose_file: Path to docker-compose.yml file.
            project_dir: Working directory for docker compose commands.
                Defaults to parent directory of compose_file.
        """
        self.compose_file = Path(compose_file)
        self.project_dir = project_dir or str(self.compose_file.parent)
        self._client: Optional[docker.DockerClient] = None

    @property
    def client(self) -> docker.DockerClient:
        """Lazy-initialize Docker client."""
        if self._client is None:
            try:
                self._client = docker.from_env()
            except docker.errors.DockerException as e:
                raise DockerManagerError(
                    f"Failed to connect to Docker daemon: {e}"
                ) from e
        return self._client

    def start_containers(self) -> None:
        """Start all containers defined in docker-compose.yml.

        Raises:
            DockerManagerError: If docker compose up fails.
        """
        logger.info("Starting Docker containers...")
        self._run_compose_command(["up", "-d"])
        logger.info("Docker containers started.")

    def stop_containers(self, remove_volumes: bool = False) -> None:
        """Stop and remove all containers.

        Args:
            remove_volumes: If True, also remove named volumes (data loss!).
        """
        logger.info("Stopping Docker containers...")
        cmd = ["down"]
        if remove_volumes:
            cmd.append("-v")
        self._run_compose_command(cmd)
        logger.info("Docker containers stopped.")

    def wait_for_ready(
        self,
        host: str,
        port: int,
        timeout: int = 120,
        interval: float = 2.0,
    ) -> bool:
        """Wait until a TCP port is accepting connections.

        Used to wait for database containers to become ready,
        especially Cassandra which takes 30-60s to initialize.

        Args:
            host: Hostname to connect to.
            port: Port number to check.
            timeout: Maximum seconds to wait.
            interval: Seconds between connection attempts.

        Returns:
            True if the port became ready within timeout.

        Raises:
            DockerManagerError: If timeout is exceeded.
        """
        logger.info(f"Waiting for {host}:{port} to become ready (timeout={timeout}s)...")
        start = time.time()

        while time.time() - start < timeout:
            if self._check_port(host, port):
                elapsed = time.time() - start
                logger.info(f"{host}:{port} is ready (took {elapsed:.1f}s)")
                return True
            time.sleep(interval)

        raise DockerManagerError(
            f"Timeout ({timeout}s) waiting for {host}:{port} to become ready"
        )

    def get_container(self, container_name: str) -> Any:
        """Get a Docker container object by name.

        Args:
            container_name: Name of the container.

        Returns:
            Docker Container object.

        Raises:
            DockerManagerError: If container is not found.
        """
        try:
            return self.client.containers.get(container_name)
        except docker.errors.NotFound:
            raise DockerManagerError(f"Container '{container_name}' not found")
        except docker.errors.APIError as e:
            raise DockerManagerError(f"Docker API error: {e}") from e

    def is_container_running(self, container_name: str) -> bool:
        """Check if a container is currently running.

        Args:
            container_name: Name of the container.

        Returns:
            True if the container is running.
        """
        try:
            container = self.client.containers.get(container_name)
            return container.status == "running"
        except (docker.errors.NotFound, docker.errors.APIError):
            return False

    def get_container_stats(self, container_name: str) -> dict[str, Any]:
        """Get a single snapshot of container resource stats.

        Args:
            container_name: Name of the container.

        Returns:
            Raw Docker stats dictionary.
        """
        container = self.get_container(container_name)
        return container.stats(stream=False)

    def _run_compose_command(self, args: list[str]) -> subprocess.CompletedProcess:
        """Run a docker compose command.

        Args:
            args: Arguments to pass after 'docker compose'.

        Returns:
            CompletedProcess result.

        Raises:
            DockerManagerError: If the command fails.
        """
        cmd = ["docker", "compose", "-f", str(self.compose_file)] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                raise DockerManagerError(
                    f"docker compose {' '.join(args)} failed:\n{result.stderr}"
                )
            return result
        except subprocess.TimeoutExpired:
            raise DockerManagerError(
                f"docker compose {' '.join(args)} timed out (300s)"
            )
        except FileNotFoundError:
            raise DockerManagerError(
                "docker command not found. Is Docker installed and in PATH?"
            )

    @staticmethod
    def _check_port(host: str, port: int, timeout: float = 2.0) -> bool:
        """Check if a TCP port is accepting connections.

        Args:
            host: Hostname to connect to.
            port: Port number.
            timeout: Connection timeout in seconds.

        Returns:
            True if connection succeeded.
        """
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (ConnectionRefusedError, TimeoutError, OSError):
            return False
