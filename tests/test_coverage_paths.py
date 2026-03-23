"""Additional tests to drive high branch coverage."""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.datastructures import MultiDict

from app import (
    build_account_columns,
    build_default_account_row,
    determine_post_login_route,
    filter_alliance_users,
    format_account_display,
    handle_option_maintenance,
    parse_accounts_form,
    require_admin,
    require_login,
    sort_accounts,
    user_or_accounts_match,
    validate_accounts,
)
from app.instrumentation import instrument
from app.security import hash_password
from app.storage import UserStore, ensure_indexes, verify_connection
from app.translations import TRANSLATIONS
from tests.test_app import create_user, extract_csrf_token, login_user, save_user_info


def test_create_account_validation_and_login_failures(client) -> None:
    access_page = client.get("/create-account-access")
    csrf_token = extract_csrf_token(access_page.get_data(as_text=True))

    invalid_csrf = client.post("/create-account-access", data={"access_code": "TNO", "csrf_token": "bad"})
    assert invalid_csrf.status_code == 400

    wrong_code = client.post(
        "/create-account-access",
        data={"access_code": "BAD", "csrf_token": csrf_token},
        follow_redirects=True,
    )
    assert "incorrect" in wrong_code.get_data(as_text=True)

    access_page = client.get("/create-account-access")
    csrf_token = extract_csrf_token(access_page.get_data(as_text=True))
    client.post(
        "/create-account-access",
        data={"access_code": "TNO", "csrf_token": csrf_token},
        follow_redirects=True,
    )

    signup_page = client.get("/create-account")
    signup_csrf = extract_csrf_token(signup_page.get_data(as_text=True))
    blank_username = client.post(
        "/create-account",
        data={
            "username": "",
            "password": "Password1!",
            "confirm_password": "Password1!",
            "csrf_token": signup_csrf,
        },
        follow_redirects=True,
    )
    assert "Username is required." in blank_username.get_data(as_text=True)

    mismatch = client.post(
        "/create-account",
        data={
            "username": "MismatchUser",
            "password": "Password1!",
            "confirm_password": "Password2!",
            "csrf_token": signup_csrf,
        },
        follow_redirects=True,
    )
    assert ">False<" in mismatch.get_data(as_text=True)

    create_user(client, "TakenCase")
    access_page = client.get("/create-account-access")
    csrf_token = extract_csrf_token(access_page.get_data(as_text=True))
    client.post("/create-account-access", data={"access_code": "TNO", "csrf_token": csrf_token}, follow_redirects=True)
    signup_page = client.get("/create-account")
    signup_csrf = extract_csrf_token(signup_page.get_data(as_text=True))
    taken = client.post(
        "/create-account",
        data={
            "username": "TakenCase",
            "password": "Password1!",
            "confirm_password": "Password1!",
            "csrf_token": signup_csrf,
        },
        follow_redirects=True,
    )
    assert "already taken" in taken.get_data(as_text=True)

    login_page = client.get("/login")
    login_csrf = extract_csrf_token(login_page.get_data(as_text=True))
    bad_login = client.post(
        "/login",
        data={"username": "TakenCase", "password": "wrong", "csrf_token": login_csrf},
        follow_redirects=True,
    )
    assert "Invalid username or password." in bad_login.get_data(as_text=True)


def test_logout_and_language_invalid_csrf(client) -> None:
    logout_response = client.post("/logout", data={"csrf_token": "bad"})
    assert logout_response.status_code == 400

    language_response = client.post("/preferences/language", data={"csrf_token": "bad"})
    assert language_response.status_code == 400


def test_user_info_reset_password_and_delete_paths(client, app) -> None:
    create_user(client, "DeleteMe")
    login_user(client, "DeleteMe")

    user_info_page = client.get("/user-info")
    csrf_token = extract_csrf_token(user_info_page.get_data(as_text=True))

    first_name_required = client.post(
        "/user-info",
        data={"csrf_token": csrf_token, "action": "save_info", "first_name": "", "preferred_language": "en"},
        follow_redirects=True,
    )
    assert "First name is required." in first_name_required.get_data(as_text=True)

    reset_fail = client.post(
        "/user-info",
        data={
            "csrf_token": csrf_token,
            "action": "reset_password",
            "new_password": "short",
            "confirm_new_password": "short",
        },
        follow_redirects=True,
    )
    assert ">False<" in reset_fail.get_data(as_text=True)

    reset_ok = client.post(
        "/user-info",
        data={
            "csrf_token": csrf_token,
            "action": "reset_password",
            "new_password": "Password9!",
            "confirm_new_password": "Password9!",
        },
        follow_redirects=True,
    )
    assert "password has been reset" in reset_ok.get_data(as_text=True)

    save_user_info(client, "Delete")
    app.config["USER_STORE"].save_accounts(
        "DeleteMe",
        [{"account_name": "DeleteMe", "account_type": "Main", "alliance": "TNO"}],
    )
    user_info_page = client.get("/user-info")
    csrf_token = extract_csrf_token(user_info_page.get_data(as_text=True))
    blocked_delete = client.post(
        "/user-info",
        data={"csrf_token": csrf_token, "action": "delete_user"},
        follow_redirects=True,
    )
    assert "only available when no accounts exist" in blocked_delete.get_data(as_text=True)

    app.config["USER_STORE"].save_accounts("DeleteMe", [])
    user_info_page = client.get("/user-info")
    csrf_token = extract_csrf_token(user_info_page.get_data(as_text=True))
    deleted = client.post(
        "/user-info",
        data={"csrf_token": csrf_token, "action": "delete_user"},
        follow_redirects=True,
    )
    assert "has been deleted" in deleted.get_data(as_text=True)


def test_accounts_form_branches_and_admin_crud(client, app) -> None:
    create_user(client, "Manager")
    login_user(client, "Manager")
    save_user_info(client, "Manage")

    accounts_page = client.get("/accounts")
    csrf_token = extract_csrf_token(accounts_page.get_data(as_text=True))

    invalid_name = client.post(
        "/accounts",
        data={
            "csrf_token": csrf_token,
            "action": "save",
            "account_name": "",
            "account_type": "Main",
            "alliance": "TNO",
        },
        follow_redirects=True,
    )
    assert "must include an account name" in invalid_name.get_data(as_text=True)

    duplicate_main = client.post(
        "/accounts",
        data={
            "csrf_token": csrf_token,
            "action": "save",
            "account_name": ["One", "Two"],
            "account_type": ["Main", "Main"],
            "alliance": ["TNO", "TCF"],
        },
        follow_redirects=True,
    )
    assert "Only one account can be marked as Main." in duplicate_main.get_data(as_text=True)

    add_row = client.post(
        "/accounts",
        data={
            "csrf_token": csrf_token,
            "action": "add",
            "account_name": ["One"],
            "account_type": ["Main"],
            "alliance": ["TNO"],
        },
        follow_redirects=True,
    )
    assert add_row.status_code == 200
    assert add_row.get_data(as_text=True).count('name="account_name"') >= 2

    delete_rows = client.post(
        "/accounts",
        data={
            "csrf_token": csrf_token,
            "action": "delete",
            "selected_rows": ["0"],
            "account_name": ["One"],
            "account_type": ["Main"],
            "alliance": ["TNO"],
        },
        follow_redirects=True,
    )
    assert "Accounts have been saved." in delete_rows.get_data(as_text=True)

    not_admin = client.get("/admin", follow_redirects=True)
    assert "Admin access is required." in not_admin.get_data(as_text=True)

    create_user(client, "Eviseration")
    login_user(client, "Eviseration")
    save_user_info(client, "Admin")

    admin_page = client.get("/admin/account-types")
    admin_csrf = extract_csrf_token(admin_page.get_data(as_text=True))

    client.post(
        "/admin/account-types",
        data={"csrf_token": admin_csrf, "action": "add", "value": "Alt"},
        follow_redirects=True,
    )
    updated = client.post(
        "/admin/account-types",
        data={"csrf_token": admin_csrf, "action": "update", "original_value": "Alt", "value": "Alt2"},
        follow_redirects=True,
    )
    assert "Admin options have been saved." in updated.get_data(as_text=True)

    client.post(
        "/admin/account-types",
        data={"csrf_token": admin_csrf, "action": "delete", "original_value": "Alt2"},
        follow_redirects=True,
    )

    alliances_page = client.get("/admin/alliances")
    alliances_csrf = extract_csrf_token(alliances_page.get_data(as_text=True))
    client.post(
        "/admin/alliances",
        data={"csrf_token": alliances_csrf, "action": "add", "value": "Custom"},
        follow_redirects=True,
    )

    user_admin_page = client.get("/admin/users")
    user_admin_csrf = extract_csrf_token(user_admin_page.get_data(as_text=True))
    save_types = client.post(
        "/admin/users",
        data={
            "csrf_token": user_admin_csrf,
            "action": "save",
            "username": ["manager", "eviseration"],
            "user_type": ["Admin", "Admin"],
        },
        follow_redirects=True,
    )
    assert "User administration changes have been saved." in save_types.get_data(as_text=True)

    delete_users = client.post(
        "/admin/users",
        data={
            "csrf_token": user_admin_csrf,
            "action": "delete",
            "selected_users": ["manager"],
            "username": ["manager", "eviseration"],
            "user_type": ["Admin", "Admin"],
        },
        follow_redirects=True,
    )
    assert "User administration changes have been saved." in delete_users.get_data(as_text=True)


def test_helper_functions_and_require_guards(app) -> None:
    store = app.config["USER_STORE"]
    user = store.create_user("HelperUser", hash_password("Password1!"))

    assert determine_post_login_route(store, user) == "user_info"
    store.update_profile("HelperUser", "Help", "", "", "")
    assert determine_post_login_route(store, user) == "accounts"

    with app.test_request_context("/"):
        redirect_response = require_login(store)
        assert redirect_response.status_code == 302

    with app.test_request_context("/"):
        from flask import session

        session["current_user"] = "ghost"
        redirect_response = require_login(store)
        assert redirect_response.status_code == 302

    with app.test_request_context("/"):
        from flask import g, session

        session["current_user"] = "helperuser"
        g.translations = {"admin_required": "Admin required"}
        redirect_response = require_admin(store)
        assert redirect_response.status_code == 302

    assert build_default_account_row("Name") == {
        "account_name": "Name",
        "account_type": "Main",
        "alliance": "TNO",
    }
    parsed = parse_accounts_form(
        type(
            "RequestObj",
            (),
            {
                "form": MultiDict(
                    [
                        ("account_name", " "),
                        ("account_name", "A"),
                        ("account_type", ""),
                        ("account_type", "Main"),
                        ("alliance", ""),
                        ("alliance", "TNO"),
                    ]
                )
            },
        )()
    )
    assert parsed == [{"account_name": "A", "account_type": "Main", "alliance": "TNO"}]
    assert validate_accounts([]) is None
    assert validate_accounts([{"account_name": "", "account_type": "Main", "alliance": "TNO"}]) == "account_name_required"
    assert (
        validate_accounts(
            [
                {"account_name": "A", "account_type": "Main", "alliance": "TNO"},
                {"account_name": "B", "account_type": "Main", "alliance": "TCF"},
            ]
        )
        == "single_main_required"
    )
    accounts = sort_accounts(
        [
            {"account_name": "farm b", "account_type": "Farm", "alliance": "R&S"},
            {"account_name": "sec", "account_type": "Secondary", "alliance": "TNO"},
            {"account_name": "main", "account_type": "Main", "alliance": "TCF"},
            {"account_name": "farm a", "account_type": "Farm", "alliance": "TNO"},
        ]
    )
    assert [item["account_name"] for item in accounts] == ["main", "sec", "farm a", "farm b"]
    assert user_or_accounts_match({"display_name": "HelperUser", "username": "helperuser"}, accounts, "farm a")
    assert not user_or_accounts_match({"display_name": "HelperUser", "username": "helperuser"}, accounts, "missing")
    columns = build_account_columns(accounts)
    assert [column["header"] for column in columns] == ["Main", "Secondary", "Farm1", "Farm2"]
    assert format_account_display({"account_name": "main", "alliance": "TCF"}) == "main (TCF)"
    filtered = filter_alliance_users(
        [
            {
                "username": "helperuser",
                "display_name": "HelperUser",
                "first_name": "Help",
                "last_name": "Er",
                "email": "h@example.com",
                "accounts": accounts,
            }
        ],
        "Farm",
        "TNO",
        "farm",
    )
    assert filtered[0]["account_columns"] == [{"header": "Farm1", "value": "farm a (TNO)"}]


def test_storage_methods_and_index_helpers(app) -> None:
    store = app.config["USER_STORE"]
    created = store.create_user("StorageUser", hash_password("Password1!"))
    assert created["user_type"] == "User"
    assert store.username_exists("StorageUser")
    assert store.get_user("StorageUser")["display_name"] == "StorageUser"
    assert store.get_accounts("Missing") == []
    assert not store.has_profile_data("Missing")
    store.update_password("StorageUser", "hash2")
    store.save_accounts("StorageUser", [{"account_name": "One", "account_type": "Main", "alliance": "TNO"}])
    assert store.has_accounts("StorageUser")
    store.update_user_type("StorageUser", "Admin")
    assert any(user["user_type"] == "Admin" for user in store.list_users() if user["username"] == "storageuser")
    store.add_option("account_types", "Scout")
    assert "Scout" in store.get_options("account_types")
    store.add_option("account_types", "   ")
    store.update_option("account_types", "Scout", "Scout+")
    assert "Scout+" in store.get_options("account_types")
    store.update_option("account_types", "Scout+", "   ")
    store.delete_option("account_types", "Scout+")
    store.save_accounts("StorageUser", [{"account_name": "One", "account_type": "Main", "alliance": "TNO"}])
    store.add_option("alliances", "Guild")
    store.update_option("alliances", "TNO", "TNOX")
    assert store.get_accounts("StorageUser")[0]["alliance"] == "TNOX"
    store.delete_user("StorageUser")
    assert store.get_user("StorageUser") is None

    duplicate_store = UserStore(
        Mock(insert_one=Mock(side_effect=DuplicateKeyError("dup")), find_one=Mock()),
        Mock(),
    )
    with pytest.raises(ValueError):
        duplicate_store.create_user("Dup", "hash")

    logger = Mock(spec=logging.Logger)
    users_collection = Mock()
    settings_collection = Mock()
    ensure_indexes(users_collection, settings_collection, "mongo://test", logger)
    users_collection.create_index.assert_called_once()
    settings_collection.create_index.assert_called_once()
    failing_collection = Mock()
    failing_collection.create_index.side_effect = PyMongoError("boom")
    ensure_indexes(failing_collection, settings_collection, "mongo://test", logger)
    assert logger.warning.called

    client = Mock()
    client.admin.command.return_value = {"ok": 1}
    verify_connection(client, "mongo://test", logger)
    client.admin.command.side_effect = PyMongoError("down")
    verify_connection(client, "mongo://test", logger)


def test_handle_option_maintenance_and_instrumentation_exception(app) -> None:
    store = app.config["USER_STORE"]

    with app.test_request_context("/admin/account-types", method="GET"):
        from flask import g

        g.translations = TRANSLATIONS["en"]
        g.language = "en"
        g.csrf_token = "token"
        g.current_user = None
        g.is_admin = False
        response = handle_option_maintenance(store, "account_types", "admin_account_types", "account_type")
        assert "Maintenance for" in response

    with app.test_request_context(
        "/admin/account-types",
        method="POST",
        data={"csrf_token": "bad", "action": "add", "value": "X"},
    ):
        response = handle_option_maintenance(store, "account_types", "admin_account_types", "account_type")
        assert response.status_code == 400

    @instrument("boom")
    def boom() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        boom()
