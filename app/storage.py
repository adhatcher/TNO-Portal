"""MongoDB-backed persistence services."""

from __future__ import annotations

import logging
from typing import Any

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.instrumentation import instrument

DEFAULT_ACCOUNT_TYPES = ["Main", "Secondary", "Farm"]
DEFAULT_ALLIANCES = ["TNO", "TCF", "TON", "R&S"]


class UserStore:
    """Persistence wrapper for users, accounts, and admin settings."""

    def __init__(self, users_collection: Collection, settings_collection: Collection) -> None:
        self._users = users_collection
        self._settings = settings_collection

    @instrument("user_store_username_exists")
    def username_exists(self, username: str) -> bool:
        """Return True when a username already exists."""

        if not username:
            return False
        return self._users.find_one({"username": username.lower()}, {"_id": 1}) is not None

    @instrument("user_store_create_user")
    def create_user(self, username: str, password_hash: str) -> dict[str, Any]:
        """Create and persist a user."""

        normalized = username.lower()
        record = {
            "username": normalized,
            "display_name": username,
            "password_hash": password_hash,
            "first_name": "",
            "last_name": "",
            "email": "",
            "preferred_language": "",
            "user_type": "Admin" if normalized == "eviseration" else "User",
            "accounts": [],
        }
        try:
            self._users.insert_one(record)
        except DuplicateKeyError as error:
            raise ValueError("Username already exists") from error
        return record

    @instrument("user_store_get_user")
    def get_user(self, username: str) -> dict[str, Any] | None:
        """Fetch a user by username."""

        return self._users.find_one({"username": username.lower()}, {"_id": 0})

    @instrument("user_store_update_profile")
    def update_profile(
        self,
        username: str,
        first_name: str,
        last_name: str,
        email: str,
        preferred_language: str,
    ) -> None:
        """Update a user's profile fields."""

        self._users.update_one(
            {"username": username.lower()},
            {
                "$set": {
                    "first_name": first_name.strip(),
                    "last_name": last_name.strip(),
                    "email": email.strip(),
                    "preferred_language": preferred_language.strip(),
                }
            },
        )

    @instrument("user_store_update_password")
    def update_password(self, username: str, password_hash: str) -> None:
        """Update a user's password hash."""

        self._users.update_one({"username": username.lower()}, {"$set": {"password_hash": password_hash}})

    @instrument("user_store_delete_user")
    def delete_user(self, username: str) -> None:
        """Delete a user and their embedded account data."""

        self._users.delete_one({"username": username.lower()})

    @instrument("user_store_list_users")
    def list_users(self) -> list[dict[str, Any]]:
        """Return all users for admin management."""

        return list(self._users.find({}, {"_id": 0}).sort("display_name", 1))

    @instrument("user_store_update_user_type")
    def update_user_type(self, username: str, user_type: str) -> None:
        """Update a user's role."""

        self._users.update_one({"username": username.lower()}, {"$set": {"user_type": user_type}})

    @instrument("user_store_get_accounts")
    def get_accounts(self, username: str) -> list[dict[str, str]]:
        """Return a user's accounts."""

        user = self.get_user(username)
        if not user:
            return []
        return user.get("accounts", [])

    @instrument("user_store_save_accounts")
    def save_accounts(self, username: str, accounts: list[dict[str, str]]) -> None:
        """Persist a user's accounts."""

        self._users.update_one({"username": username.lower()}, {"$set": {"accounts": accounts}})

    @instrument("user_store_has_accounts")
    def has_accounts(self, username: str) -> bool:
        """Return True when a user has saved accounts."""

        return bool(self.get_accounts(username))

    @instrument("user_store_has_profile_data")
    def has_profile_data(self, username: str) -> bool:
        """Return True if any profile field is populated."""

        user = self.get_user(username)
        if not user:
            return False
        return any(
            bool(user.get(field))
            for field in ("first_name", "last_name", "email", "preferred_language")
        )

    @instrument("user_store_get_options")
    def get_options(self, category: str) -> list[str]:
        """Return admin-managed option values."""

        self._seed_option_defaults(category)
        records = list(self._settings.find({"category": category}, {"_id": 0}).sort("value", 1))
        return [record["value"] for record in records]

    @instrument("user_store_add_option")
    def add_option(self, category: str, value: str) -> None:
        """Create a new admin-managed option."""

        cleaned = value.strip()
        if not cleaned:
            return
        self._settings.update_one(
            {"category": category, "value": cleaned},
            {"$setOnInsert": {"category": category, "value": cleaned}},
            upsert=True,
        )

    @instrument("user_store_update_option")
    def update_option(self, category: str, original_value: str, new_value: str) -> None:
        """Rename an admin-managed option."""

        cleaned = new_value.strip()
        if not cleaned:
            return
        self._settings.update_one(
            {"category": category, "value": original_value},
            {"$set": {"value": cleaned}},
        )
        self._replace_account_option(category, original_value, cleaned)

    @instrument("user_store_delete_option")
    def delete_option(self, category: str, value: str) -> None:
        """Delete an admin-managed option."""

        self._settings.delete_one({"category": category, "value": value})

    @instrument("user_store_seed_defaults")
    def seed_defaults(self) -> None:
        """Ensure required settings defaults exist."""

        self._seed_option_defaults("account_types")
        self._seed_option_defaults("alliances")

    @instrument("user_store_seed_option_defaults")
    def _seed_option_defaults(self, category: str) -> None:
        """Seed default options when a category is empty."""

        if self._settings.find_one({"category": category}, {"_id": 1}) is not None:
            return

        defaults = DEFAULT_ACCOUNT_TYPES if category == "account_types" else DEFAULT_ALLIANCES
        self._settings.insert_many([{"category": category, "value": value} for value in defaults])

    @instrument("user_store_replace_account_option")
    def _replace_account_option(self, category: str, original_value: str, new_value: str) -> None:
        """Propagate renamed account options into embedded account records."""

        field_name = "account_type" if category == "account_types" else "alliance"
        users = self._users.find({f"accounts.{field_name}": original_value}, {"_id": 0, "username": 1, "accounts": 1})
        for user in users:
            updated_accounts = []
            for account in user.get("accounts", []):
                updated_account = dict(account)
                if updated_account.get(field_name) == original_value:
                    updated_account[field_name] = new_value
                updated_accounts.append(updated_account)
            self.save_accounts(user["username"], updated_accounts)


@instrument("create_user_store")
def create_user_store(config: dict[str, Any]) -> UserStore:
    """Build a Mongo-backed user store from app configuration."""

    logger = logging.getLogger("tno")
    client_factory = config.get("MONGO_CLIENT_FACTORY") or MongoClient
    client = client_factory(
        config["MONGO_URI"],
        serverSelectionTimeoutMS=config["MONGO_SERVER_SELECTION_TIMEOUT_MS"],
        connect=False,
    )
    verify_connection(client, config["MONGO_URI"], logger)
    database = client[config["MONGO_DB_NAME"]]
    users_collection = database["users"]
    settings_collection = database["settings"]
    ensure_indexes(users_collection, settings_collection, config["MONGO_URI"], logger)
    store = UserStore(users_collection, settings_collection)
    store.seed_defaults()
    return store


@instrument("ensure_indexes")
def ensure_indexes(
    users_collection: Collection,
    settings_collection: Collection,
    mongo_uri: str,
    logger: logging.Logger,
) -> None:
    """Create required Mongo indexes when possible."""

    try:
        users_collection.create_index("username", unique=True)
        settings_collection.create_index([("category", 1), ("value", 1)], unique=True)
    except PyMongoError as error:
        logger.warning("Could not create MongoDB indexes during startup for %s: %s", mongo_uri, error)


@instrument("verify_connection")
def verify_connection(client: MongoClient, mongo_uri: str, logger: logging.Logger) -> None:
    """Log MongoDB connectivity status during startup."""

    try:
        client.admin.command("ping")
        logger.info("Connected to MongoDB at %s", mongo_uri)
    except PyMongoError as error:
        logger.warning("Could not connect to MongoDB at %s during startup: %s", mongo_uri, error)
