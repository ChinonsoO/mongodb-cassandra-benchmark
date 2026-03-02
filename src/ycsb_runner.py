"""YCSB benchmark execution via subprocess.

Handles constructing and running YCSB commands for both
MongoDB and Cassandra benchmarks.

Instead of relying on the stock ycsb / ycsb.bat shell scripts
(which cannot handle paths containing spaces), this module
resolves the Java classpath directly in Python and invokes
java / java.exe via subprocess.  This works identically on
Windows, macOS and Linux.
"""

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Binding name -> Java DB client class (subset used by this project)
_BINDING_CLASSES: dict[str, str] = {
    "mongodb": "site.ycsb.db.MongoDbClient",
    "mongodb-async": "site.ycsb.db.AsyncMongoDbClient",
    "cassandra-cql": "site.ycsb.db.CassandraCQLClient",
    "cassandra2-cql": "site.ycsb.db.CassandraCQLClient",
}


class YCSBError(Exception):
    """Raised when a YCSB operation fails."""


class YCSBRunner:
    """Execute YCSB load and run phases via subprocess.

    Wraps the YCSB command-line tool, constructing the correct
    arguments for each database binding and workload configuration.

    Always invokes Java directly (bypassing ycsb.bat / ycsb shell
    scripts) so that paths with spaces are handled correctly on
    every operating system.
    """

    def __init__(
        self,
        ycsb_path: str = "ycsb-0.17.0",
        java_home: Optional[str] = None,
    ):
        """Initialize YCSBRunner.

        Args:
            ycsb_path: Path to the YCSB installation directory.
            java_home: Optional explicit path to a Java installation
                (e.g. ``/usr/lib/jvm/java-17``).  When provided this
                takes priority over the ``JAVA_HOME`` environment
                variable.  If neither is set, ``java`` must be on
                the system ``PATH``.
        """
        self.ycsb_path = Path(ycsb_path).resolve()
        self._java_home = java_home
        self._validate_installation()
        # Pre-load binding map from bindings.properties
        self._bindings = self._load_bindings()

    def _validate_installation(self) -> None:
        """Verify YCSB is installed (lib directory present)."""
        lib_dir = self.ycsb_path / "lib"
        if not lib_dir.exists():
            logger.warning(
                f"YCSB lib directory not found at {lib_dir}. "
                "Run setup_ycsb.py to download YCSB."
            )

    def _load_bindings(self) -> dict[str, str]:
        """Load binding name -> class mappings from bindings.properties.

        Returns:
            Dictionary mapping binding names to their Java class names.
        """
        bindings = dict(_BINDING_CLASSES)  # start with built-in defaults
        props_file = self.ycsb_path / "bin" / "bindings.properties"
        if props_file.exists():
            for line in props_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    name, cls = line.split(":", 1)
                    bindings[name.strip()] = cls.strip()
        return bindings

    def _get_java_executable(self) -> str:
        """Resolve the path to the ``java`` executable.

        Resolution order:
        1. Explicit ``java_home`` passed to the constructor.
        2. ``JAVA_HOME`` environment variable.
        3. ``java`` on the system ``PATH``.

        Returns:
            Path (or bare name) of the Java executable.

        Raises:
            YCSBError: If Java cannot be found by any method.
        """
        # 1. Explicit java_home from constructor / config
        java_home = self._java_home or os.environ.get("JAVA_HOME", "")
        if java_home:
            java_bin = Path(java_home) / "bin" / "java"
            if platform.system() == "Windows":
                java_bin = java_bin.with_suffix(".exe")
            if java_bin.exists():
                return str(java_bin)
            logger.warning(
                f"Java not found at {java_bin} (from "
                f"{'--java-home / config' if self._java_home else 'JAVA_HOME'}). "
                "Falling back to PATH lookup."
            )

        # 2. Fallback: 'java' on PATH
        if shutil.which("java"):
            return "java"

        raise YCSBError(
            "Java executable not found. Please do one of the following:\n"
            "  1. Set JAVA_HOME to your JDK installation directory, OR\n"
            "  2. Pass --java-home <path> on the command line, OR\n"
            "  3. Set 'java_home' under 'ycsb' in configs/experiment.yaml, OR\n"
            "  4. Ensure 'java' is on your system PATH."
        )

    def _build_classpath(self, binding: str) -> str:
        """Build the Java classpath for a given binding.

        Collects:
          - YCSB conf directory
          - All jars in YCSB lib/
          - Binding conf directory (if present)
          - All jars in binding lib/

        Args:
            binding: YCSB binding name (e.g., 'cassandra-cql').

        Returns:
            Classpath string with entries separated by the OS path separator.
        """
        entries: list[str] = []

        # Resolve binding directory name (strip version suffix like cassandra-cql -> cassandra)
        binding_dir = binding.split("-")[0]

        # Conf directory
        conf_dir = self.ycsb_path / "conf"
        if conf_dir.exists():
            entries.append(str(conf_dir))

        # Core library jars
        lib_dir = self.ycsb_path / "lib"
        if lib_dir.exists():
            for jar in sorted(lib_dir.glob("*.jar")):
                entries.append(str(jar))

        # Binding conf directory
        binding_conf = self.ycsb_path / f"{binding_dir}-binding" / "conf"
        if binding_conf.exists():
            entries.append(str(binding_conf))

        # Binding library jars
        binding_lib = self.ycsb_path / f"{binding_dir}-binding" / "lib"
        if binding_lib.exists():
            for jar in sorted(binding_lib.glob("*.jar")):
                entries.append(str(jar))

        return os.pathsep.join(entries)

    def _get_binding_class(self, binding: str) -> str:
        """Look up the Java class for a YCSB binding.

        Args:
            binding: Binding name (e.g., 'cassandra-cql').

        Returns:
            Fully-qualified Java class name.

        Raises:
            YCSBError: If the binding is not recognized.
        """
        bindings = getattr(self, "_bindings", _BINDING_CLASSES)
        cls = bindings.get(binding)
        if not cls:
            raise YCSBError(
                f"Unknown YCSB binding '{binding}'. "
                f"Available bindings: {sorted(bindings.keys())}"
            )
        return cls

    def load(
        self,
        binding: str,
        workload_file: str,
        properties: dict[str, Any] | None = None,
        timeout: int = 3600,
    ) -> str:
        """Run the YCSB load phase to populate the database.

        Args:
            binding: YCSB database binding name (e.g., 'mongodb', 'cassandra-cql').
            workload_file: Path to the YCSB workload properties file.
            properties: Additional YCSB properties to pass via -p flags.
            timeout: Maximum seconds to wait for the command to complete.

        Returns:
            Raw stdout output from YCSB.

        Raises:
            YCSBError: If the YCSB command fails.
        """
        return self._execute("load", binding, workload_file, properties, timeout)

    def run(
        self,
        binding: str,
        workload_file: str,
        properties: dict[str, Any] | None = None,
        timeout: int = 3600,
    ) -> str:
        """Run the YCSB run phase to execute the workload.

        Args:
            binding: YCSB database binding name.
            workload_file: Path to the YCSB workload properties file.
            properties: Additional YCSB properties to pass via -p flags.
            timeout: Maximum seconds to wait for the command to complete.

        Returns:
            Raw stdout output from YCSB.

        Raises:
            YCSBError: If the YCSB command fails.
        """
        return self._execute("run", binding, workload_file, properties, timeout)

    def build_command(
        self,
        phase: str,
        binding: str,
        workload_file: str,
        properties: dict[str, Any] | None = None,
    ) -> list[str]:
        """Build the YCSB command line arguments.

        Constructs a direct ``java`` invocation with the correct
        classpath, YCSB client class and database binding class.

        Args:
            phase: Either 'load' or 'run'.
            binding: YCSB database binding name.
            workload_file: Path to the workload properties file.
            properties: Additional properties to pass via -p flags.

        Returns:
            List of command line arguments.
        """
        java_bin = self._get_java_executable()
        classpath = self._build_classpath(binding)
        binding_class = self._get_binding_class(binding)

        ycsb_command = "-load" if phase == "load" else "-t"
        ycsb_class = "site.ycsb.Client"

        cmd = [
            java_bin,
            "-classpath", classpath,
            ycsb_class,
            ycsb_command,
            "-db", binding_class,
            "-s",
            "-P", workload_file,
        ]

        if properties:
            for key, value in properties.items():
                cmd.extend(["-p", f"{key}={value}"])

        return cmd

    def _execute(
        self,
        phase: str,
        binding: str,
        workload_file: str,
        properties: dict[str, Any] | None,
        timeout: int,
    ) -> str:
        """Execute a YCSB command and return stdout.

        Args:
            phase: 'load' or 'run'.
            binding: Database binding name.
            workload_file: Path to workload properties file.
            properties: Additional YCSB properties.
            timeout: Command timeout in seconds.

        Returns:
            Raw stdout from YCSB.

        Raises:
            YCSBError: On non-zero exit code or timeout.
        """
        cmd = self.build_command(phase, binding, workload_file, properties)
        cmd_display = " ".join(f'"{c}"' if " " in c else c for c in cmd)
        logger.info(f"Running YCSB {phase}: {cmd_display}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.ycsb_path.parent),
            )

            # Log stderr (YCSB progress output goes to stderr)
            if result.stderr:
                logger.debug(f"YCSB stderr:\n{result.stderr}")

            if result.returncode != 0:
                raise YCSBError(
                    f"YCSB {phase} failed (exit code {result.returncode}):\n"
                    f"stdout: {result.stdout}\n"
                    f"stderr: {result.stderr}"
                )

            return result.stdout

        except subprocess.TimeoutExpired:
            raise YCSBError(f"YCSB {phase} timed out after {timeout}s")
        except FileNotFoundError:
            raise YCSBError(
                "Java executable not found. Please do one of the following:\n"
                "  1. Set JAVA_HOME to your JDK installation directory, OR\n"
                "  2. Pass --java-home <path> on the command line, OR\n"
                "  3. Set 'java_home' under 'ycsb' in configs/experiment.yaml, OR\n"
                "  4. Ensure 'java' is on your system PATH."
            )

    @staticmethod
    def get_binding_properties(db_type: str) -> dict[str, str]:
        """Get the default YCSB connection properties for a database type.

        Args:
            db_type: Either 'mongodb' or 'cassandra'.

        Returns:
            Dictionary of YCSB properties for connecting to the database.

        Raises:
            ValueError: If db_type is not recognized.
        """
        if db_type == "mongodb":
            return {
                "mongodb.url": "mongodb://localhost:27017/ycsb?w=1",
            }
        elif db_type == "cassandra":
            return {
                "hosts": "localhost",
                "cassandra.readconsistencylevel": "ONE",
                "cassandra.writeconsistencylevel": "ONE",
            }
        else:
            raise ValueError(f"Unknown database type: {db_type}")

    @staticmethod
    def get_binding_name(db_type: str) -> str:
        """Get the YCSB binding name for a database type.

        Args:
            db_type: Either 'mongodb' or 'cassandra'.

        Returns:
            YCSB binding name string.
        """
        binding_map = {
            "mongodb": "mongodb",
            "cassandra": "cassandra-cql",
        }
        if db_type not in binding_map:
            raise ValueError(f"Unknown database type: {db_type}")
        return binding_map[db_type]
