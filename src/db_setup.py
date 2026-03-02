"""Database schema setup and teardown for YCSB benchmarks."""

import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

# Cassandra CQL statements for YCSB schema
CASSANDRA_CREATE_KEYSPACE = """
CREATE KEYSPACE IF NOT EXISTS ycsb
WITH REPLICATION = {'class': 'SimpleStrategy', 'replication_factor': 1};
"""

CASSANDRA_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS ycsb.usertable (
    y_id varchar PRIMARY KEY,
    field0 varchar,
    field1 varchar,
    field2 varchar,
    field3 varchar,
    field4 varchar,
    field5 varchar,
    field6 varchar,
    field7 varchar,
    field8 varchar,
    field9 varchar
);
"""

CASSANDRA_TRUNCATE_TABLE = "TRUNCATE ycsb.usertable;"
CASSANDRA_DROP_KEYSPACE = "DROP KEYSPACE IF EXISTS ycsb;"


def setup_cassandra(host: str = "localhost", port: int = 9042) -> None:
    """Create the YCSB keyspace and usertable in Cassandra.

    Args:
        host: Cassandra host address.
        port: Cassandra CQL native transport port.

    Raises:
        ConnectionError: If unable to connect to Cassandra.
        RuntimeError: If schema creation fails.
    """
    from cassandra.cluster import Cluster
    from cassandra.policies import RoundRobinPolicy

    logger.info(f"Setting up Cassandra schema at {host}:{port}...")

    try:
        cluster = Cluster([host], port=port, protocol_version=4,
                          load_balancing_policy=RoundRobinPolicy())
        session = cluster.connect()

        session.execute(CASSANDRA_CREATE_KEYSPACE)
        session.execute(CASSANDRA_CREATE_TABLE)

        logger.info("Cassandra schema created successfully.")
    except Exception as e:
        raise RuntimeError(f"Failed to set up Cassandra schema: {e}") from e
    finally:
        try:
            cluster.shutdown()
        except Exception:
            pass


def reset_cassandra(host: str = "localhost", port: int = 9042) -> None:
    """Drop and recreate the YCSB keyspace in Cassandra for a clean state.

    Uses DROP KEYSPACE + recreate instead of TRUNCATE so that Cassandra
    actually removes the underlying SSTable files.  After the schema is
    rebuilt we also ask ``nodetool clearsnapshot`` (inside the Docker
    container) to remove any auto-snapshots created by the DROP, freeing
    the disk space that large datasets (e.g. 10 GB) would otherwise leave
    behind.

    Args:
        host: Cassandra host address.
        port: Cassandra CQL native transport port.
    """
    from cassandra.cluster import Cluster
    from cassandra.policies import RoundRobinPolicy

    logger.info("Resetting Cassandra (drop + recreate keyspace)...")

    try:
        cluster = Cluster([host], port=port, protocol_version=4,
                          load_balancing_policy=RoundRobinPolicy())
        session = cluster.connect()

        # Drop the entire keyspace — deletes SSTables on disk
        session.execute(CASSANDRA_DROP_KEYSPACE)
        # Recreate keyspace and table so YCSB can load fresh data
        session.execute(CASSANDRA_CREATE_KEYSPACE)
        session.execute(CASSANDRA_CREATE_TABLE)

        logger.info("Cassandra keyspace recreated.")
    except Exception as e:
        raise RuntimeError(f"Failed to reset Cassandra: {e}") from e
    finally:
        try:
            cluster.shutdown()
        except Exception:
            pass

    # Clear auto-snapshots inside the container to reclaim disk space.
    _clear_cassandra_snapshots()


def _clear_cassandra_snapshots(container_name: str = "ycsb-cassandra") -> None:
    """Run ``nodetool clearsnapshot`` inside the Cassandra container.

    Cassandra creates automatic snapshots on DROP / TRUNCATE operations.
    These snapshots consume disk space and are not needed between
    benchmark runs, so we remove them.

    This is a best-effort cleanup — if it fails (e.g. container not
    reachable), we log a warning and continue.

    Args:
        container_name: Name of the Docker container running Cassandra.
    """
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "nodetool", "clearsnapshot", "--all"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            logger.info("Cassandra snapshots cleared — disk space reclaimed.")
        else:
            logger.warning(
                f"nodetool clearsnapshot returned code {result.returncode}: "
                f"{result.stderr.strip()}"
            )
    except FileNotFoundError:
        logger.warning(
            "docker CLI not found — skipping Cassandra snapshot cleanup. "
            "Disk space from previous runs may not be reclaimed."
        )
    except subprocess.TimeoutExpired:
        logger.warning("nodetool clearsnapshot timed out after 60s — skipping.")
    except Exception as e:
        logger.warning(f"Failed to clear Cassandra snapshots: {e}")


def teardown_cassandra(host: str = "localhost", port: int = 9042) -> None:
    """Drop the YCSB keyspace in Cassandra.

    Args:
        host: Cassandra host address.
        port: Cassandra CQL native transport port.
    """
    from cassandra.cluster import Cluster
    from cassandra.policies import RoundRobinPolicy

    logger.info("Tearing down Cassandra YCSB keyspace...")

    try:
        cluster = Cluster([host], port=port, protocol_version=4,
                          load_balancing_policy=RoundRobinPolicy())
        session = cluster.connect()
        session.execute(CASSANDRA_DROP_KEYSPACE)
        logger.info("Cassandra YCSB keyspace dropped.")
    except Exception as e:
        raise RuntimeError(f"Failed to tear down Cassandra: {e}") from e
    finally:
        try:
            cluster.shutdown()
        except Exception:
            pass


def setup_mongodb(host: str = "localhost", port: int = 27017) -> None:
    """Verify MongoDB connection and ensure the ycsb database exists.

    MongoDB auto-creates databases/collections on first insert,
    so this mainly serves as a connectivity check.

    Args:
        host: MongoDB host address.
        port: MongoDB port.

    Raises:
        ConnectionError: If unable to connect to MongoDB.
    """
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure

    logger.info(f"Verifying MongoDB connection at {host}:{port}...")

    try:
        client = MongoClient(host, port, serverSelectionTimeoutMS=5000)
        # Force a connection attempt
        client.admin.command("ping")
        logger.info("MongoDB connection verified.")
    except ConnectionFailure as e:
        raise ConnectionError(f"Failed to connect to MongoDB: {e}") from e
    finally:
        try:
            client.close()
        except Exception:
            pass


def reset_mongodb(host: str = "localhost", port: int = 27017) -> None:
    """Drop the YCSB database in MongoDB for a clean state.

    Args:
        host: MongoDB host address.
        port: MongoDB port.
    """
    from pymongo import MongoClient

    logger.info("Resetting MongoDB (dropping ycsb database)...")

    try:
        client = MongoClient(host, port, serverSelectionTimeoutMS=5000)
        client.drop_database("ycsb")
        logger.info("MongoDB ycsb database dropped.")
    except Exception as e:
        raise RuntimeError(f"Failed to reset MongoDB: {e}") from e
    finally:
        try:
            client.close()
        except Exception:
            pass


def setup_database(db_type: str, host: str = "localhost", port: Optional[int] = None) -> None:
    """Set up the database schema based on database type.

    Args:
        db_type: Either 'mongodb' or 'cassandra'.
        host: Database host address.
        port: Database port (uses default if None).

    Raises:
        ValueError: If db_type is not recognized.
    """
    if db_type == "mongodb":
        setup_mongodb(host, port or 27017)
    elif db_type == "cassandra":
        setup_cassandra(host, port or 9042)
    else:
        raise ValueError(f"Unknown database type: {db_type}")


def reset_database(db_type: str, host: str = "localhost", port: Optional[int] = None) -> None:
    """Reset the database for a clean state between benchmark runs.

    Args:
        db_type: Either 'mongodb' or 'cassandra'.
        host: Database host address.
        port: Database port (uses default if None).

    Raises:
        ValueError: If db_type is not recognized.
    """
    if db_type == "mongodb":
        reset_mongodb(host, port or 27017)
    elif db_type == "cassandra":
        reset_cassandra(host, port or 9042)
    else:
        raise ValueError(f"Unknown database type: {db_type}")
