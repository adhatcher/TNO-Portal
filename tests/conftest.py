"""Pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import mongomock
import pytest

from app import create_app
from app.config import Config


class TestConfig(Config):
    TESTING = True


@pytest.fixture()
def app(tmp_path: Path):
    """Create a Flask app configured for testing."""

    TestConfig.APP_DATA_DIR = tmp_path
    TestConfig.LOG_PATH = tmp_path / "app.log"
    TestConfig.MONGO_URI = "mongodb://localhost:27017/"
    TestConfig.MONGO_DB_NAME = "tno-test-db"
    TestConfig.MONGO_COLLECTION_NAME = "users"
    TestConfig.MONGO_CLIENT_FACTORY = mongomock.MongoClient
    application = create_app(TestConfig)
    yield application


@pytest.fixture()
def client(app):
    """Create a test client."""

    return app.test_client()
