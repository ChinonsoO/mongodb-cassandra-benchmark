"""Tests for the database setup module."""

import sys
from unittest.mock import MagicMock, patch, call

import pytest

from src.db_setup import (
    setup_database,
    reset_database,
    CASSANDRA_CREATE_KEYSPACE,
    CASSANDRA_CREATE_TABLE,
    CASSANDRA_TRUNCATE_TABLE,
    CASSANDRA_DROP_KEYSPACE,
)


def _make_cassandra_mocks():
    """Create mock cassandra.cluster module and components."""
    mock_module = MagicMock()
    mock_session = MagicMock()
    mock_cluster = MagicMock()
    mock_cluster.connect.return_value = mock_session
    mock_module.Cluster.return_value = mock_cluster
    return mock_module, mock_cluster, mock_session


class TestSetupCassandra:
    """Tests for Cassandra schema setup."""

    def test_creates_keyspace_and_table(self):
        """Should execute CREATE KEYSPACE and CREATE TABLE statements."""
        mock_module, mock_cluster, mock_session = _make_cassandra_mocks()

        with patch.dict(sys.modules, {"cassandra.cluster": mock_module}):
            from src.db_setup import setup_cassandra
            setup_cassandra("localhost", 9042)

        # Verify both SQL statements were executed
        calls = mock_session.execute.call_args_list
        assert len(calls) == 2

    def test_shuts_down_cluster(self):
        """Should shut down the Cassandra cluster connection."""
        mock_module, mock_cluster, mock_session = _make_cassandra_mocks()

        with patch.dict(sys.modules, {"cassandra.cluster": mock_module}):
            from src.db_setup import setup_cassandra
            setup_cassandra()

        mock_cluster.shutdown.assert_called_once()


class TestResetCassandra:
    """Tests for Cassandra reset."""

    @patch("src.db_setup._clear_cassandra_snapshots")
    def test_drops_and_recreates_keyspace(self, mock_clear):
        """Should drop keyspace, recreate it, and clear snapshots."""
        mock_module, mock_cluster, mock_session = _make_cassandra_mocks()

        with patch.dict(sys.modules, {"cassandra.cluster": mock_module}):
            from src.db_setup import reset_cassandra
            reset_cassandra()

        # Should execute DROP, CREATE KEYSPACE, CREATE TABLE (3 calls)
        assert mock_session.execute.call_count == 3
        mock_clear.assert_called_once()


class TestSetupMongodb:
    """Tests for MongoDB setup."""

    @patch("pymongo.MongoClient")
    def test_pings_server(self, mock_client_cls):
        """Should ping the MongoDB server to verify connection."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        from src.db_setup import setup_mongodb
        setup_mongodb()

        mock_client.admin.command.assert_called_once_with("ping")

    @patch("pymongo.MongoClient")
    def test_closes_connection(self, mock_client_cls):
        """Should close the MongoDB client."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        from src.db_setup import setup_mongodb
        setup_mongodb()

        mock_client.close.assert_called_once()


class TestResetMongodb:
    """Tests for MongoDB reset."""

    @patch("pymongo.MongoClient")
    def test_drops_database(self, mock_client_cls):
        """Should drop the ycsb database."""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        from src.db_setup import reset_mongodb
        reset_mongodb()

        mock_client.drop_database.assert_called_once_with("ycsb")


class TestSetupDatabase:
    """Tests for the generic setup_database dispatcher."""

    @patch("src.db_setup.setup_mongodb")
    def test_mongodb(self, mock_setup):
        """Should dispatch to setup_mongodb."""
        setup_database("mongodb")
        mock_setup.assert_called_once_with("localhost", 27017)

    @patch("src.db_setup.setup_cassandra")
    def test_cassandra(self, mock_setup):
        """Should dispatch to setup_cassandra."""
        setup_database("cassandra")
        mock_setup.assert_called_once_with("localhost", 9042)

    def test_unknown_raises(self):
        """Should raise ValueError for unknown db type."""
        with pytest.raises(ValueError, match="Unknown database type"):
            setup_database("redis")


class TestResetDatabase:
    """Tests for the generic reset_database dispatcher."""

    @patch("src.db_setup.reset_mongodb")
    def test_mongodb(self, mock_reset):
        """Should dispatch to reset_mongodb."""
        reset_database("mongodb")
        mock_reset.assert_called_once_with("localhost", 27017)

    @patch("src.db_setup.reset_cassandra")
    def test_cassandra(self, mock_reset):
        """Should dispatch to reset_cassandra."""
        reset_database("cassandra")
        mock_reset.assert_called_once_with("localhost", 9042)

    def test_unknown_raises(self):
        """Should raise ValueError for unknown db type."""
        with pytest.raises(ValueError, match="Unknown database type"):
            reset_database("redis")

    @patch("src.db_setup.reset_mongodb")
    def test_custom_port(self, mock_reset):
        """Should pass custom port."""
        reset_database("mongodb", host="remote", port=27018)
        mock_reset.assert_called_once_with("remote", 27018)
