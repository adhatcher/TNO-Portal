"""Application configuration."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    """Base configuration for the Flask application."""

    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    APP_DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(BASE_DIR / "data")))
    LOG_PATH = APP_DATA_DIR / "app.log"
    METRICS_PATH = APP_DATA_DIR / "metrics.prom"
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://192.168.215.2:27017/")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "TNO-MongoDB")
    MONGO_COLLECTION_NAME = os.getenv("MONGO_COLLECTION_NAME", "users")
    MONGO_SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "2000"))
    MONGO_CLIENT_FACTORY = None
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_NAME = "tno_username"
    LANGUAGE_COOKIE_NAME = "tno_language"
    SUPPORTED_LANGUAGES = ("en", "fr", "es", "ru", "pt")
    INVITE_CODE = "TNO"
