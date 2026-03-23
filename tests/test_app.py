"""Application tests."""

from __future__ import annotations

import re

import pytest


def extract_csrf_token(response_text: str) -> str:
    """Extract the CSRF token from HTML."""

    match = re.search(r'name="csrf_token" value="([^"]+)"', response_text)
    assert match
    return match.group(1)


def change_language(client, page_path: str, language: str = "fr") -> str:
    """Change the UI language from a given page and return refreshed HTML."""

    page = client.get(page_path)
    csrf_token = extract_csrf_token(page.get_data(as_text=True))
    response = client.post(
        "/preferences/language",
        data={"language": language, "csrf_token": csrf_token, "next_path": page_path},
        follow_redirects=True,
    )

    assert response.status_code == 200
    return response.get_data(as_text=True)


def complete_access_code(client) -> None:
    """Complete the TNO access-code gate."""

    access_page = client.get("/create-account-access")
    csrf_token = extract_csrf_token(access_page.get_data(as_text=True))
    client.post(
        "/create-account-access",
        data={"access_code": "TNO", "csrf_token": csrf_token},
        follow_redirects=True,
    )


def create_user(client, username: str, password: str = "Password1!") -> None:
    """Create a new user through the signup flow."""

    complete_access_code(client)
    signup_page = client.get("/create-account")
    signup_csrf = extract_csrf_token(signup_page.get_data(as_text=True))
    client.post(
        "/create-account",
        data={
            "username": username,
            "password": password,
            "confirm_password": password,
            "csrf_token": signup_csrf,
        },
        follow_redirects=True,
    )
    client.post("/logout", data={"csrf_token": signup_csrf}, follow_redirects=True)


def login_user(client, username: str, password: str = "Password1!"):
    """Log a user in through the login flow."""

    login_page = client.get("/login")
    login_csrf = extract_csrf_token(login_page.get_data(as_text=True))
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": login_csrf},
        follow_redirects=False,
    )


def save_user_info(client, first_name: str, preferred_language: str = "en") -> None:
    """Save required user info for the current logged-in user."""

    user_info_page = client.get("/user-info")
    csrf_token = extract_csrf_token(user_info_page.get_data(as_text=True))
    client.post(
        "/user-info",
        data={
            "csrf_token": csrf_token,
            "action": "save_info",
            "first_name": first_name,
            "last_name": "",
            "email": "",
            "preferred_language": preferred_language,
        },
        follow_redirects=True,
    )


def test_welcome_page_loads(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert b"TNO" in response.data


def test_language_preference_is_stored(client) -> None:
    page = client.get("/")
    csrf_token = extract_csrf_token(page.get_data(as_text=True))

    response = client.post(
        "/preferences/language",
        data={"language": "fr", "csrf_token": csrf_token, "next_path": "/"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "tno_language=fr" in response.headers["Set-Cookie"]


@pytest.mark.parametrize(
    ("page_path", "expected_text"),
    [
        ("/", "Bienvenue dans la maison de TNO"),
        ("/login", "Connexion"),
        ("/create-account-access", "Saisissez le code de creation de compte"),
    ],
)
def test_language_change_refreshes_public_pages_in_selected_language(
    client, page_path: str, expected_text: str
) -> None:
    content = change_language(client, page_path)

    assert expected_text in content
    assert "Parametres de langue" in content


def test_language_change_refreshes_create_account_page_in_selected_language(client) -> None:
    complete_access_code(client)
    content = change_language(client, "/create-account")

    assert "Creez votre compte" in content
    assert "Verifier le mot de passe" in content
    assert "Parametres de langue" in content


def test_language_change_refreshes_public_pages_in_german(client) -> None:
    content = change_language(client, "/", language="de")

    assert "Willkommen im Zuhause von TNO" in content
    assert "Spracheinstellungen" in content


def test_access_code_required_before_signup(client) -> None:
    response = client.get("/create-account", follow_redirects=False)

    assert response.status_code == 302
    assert "/create-account-access" in response.headers["Location"]


def test_can_create_account_and_redirect_to_user_info(client) -> None:
    complete_access_code(client)
    signup_page = client.get("/create-account")
    signup_csrf = extract_csrf_token(signup_page.get_data(as_text=True))
    response = client.post(
        "/create-account",
        data={
            "username": "PlayerOne",
            "password": "Password1!",
            "confirm_password": "Password1!",
            "csrf_token": signup_csrf,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/user-info")
    assert any("tno_username=PlayerOne" in cookie for cookie in response.headers.getlist("Set-Cookie"))


def test_login_redirects_to_user_info_until_profile_is_completed(client) -> None:
    create_user(client, "AllianceLead")

    response = login_user(client, "AllianceLead")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/user-info")


def test_saving_user_info_redirects_to_accounts(client) -> None:
    create_user(client, "ProfileUser")
    login_user(client, "ProfileUser")

    user_info_page = client.get("/user-info")
    csrf_token = extract_csrf_token(user_info_page.get_data(as_text=True))
    response = client.post(
        "/user-info",
        data={
            "csrf_token": csrf_token,
            "action": "save_info",
            "first_name": "Taylor",
            "last_name": "Player",
            "email": "taylor@example.com",
            "preferred_language": "en",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/accounts")


def test_accounts_page_defaults_first_row_when_no_accounts_exist(client) -> None:
    create_user(client, "DefaultRow")
    login_user(client, "DefaultRow")
    user_info_page = client.get("/user-info")
    csrf_token = extract_csrf_token(user_info_page.get_data(as_text=True))
    client.post(
        "/user-info",
        data={
            "csrf_token": csrf_token,
            "action": "save_info",
            "first_name": "Default",
            "last_name": "",
            "email": "",
            "preferred_language": "en",
        },
        follow_redirects=True,
    )

    response = client.get("/accounts")
    content = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Player Accounts for DefaultRow" in content
    assert 'value="DefaultRow"' in content


def test_username_availability_endpoint(client) -> None:
    create_user(client, "TakenName")

    response = client.get("/api/username-available?username=TakenName")

    assert response.status_code == 200
    assert response.get_json()["available"] is False


def test_eviseration_is_admin_by_default_and_can_access_admin_pages(client) -> None:
    create_user(client, "Eviseration")
    response = login_user(client, "Eviseration")

    assert response.status_code == 302
    admin_response = client.get("/admin")
    assert admin_response.status_code == 200
    assert "Admin" in admin_response.get_data(as_text=True)


def test_metrics_endpoint(client) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert b"tno_function_calls_total" in response.data


def test_alliance_users_page_search_and_filters(client, app) -> None:
    create_user(client, "Eviseration")
    login_user(client, "Eviseration")
    save_user_info(client, "Aaron")

    user_store = app.config["USER_STORE"]
    user_store.save_accounts(
        "Eviseration",
        [
            {"account_name": "Baby Vis Doot Doot", "account_type": "Farm", "alliance": "R&S"},
            {"account_name": "The Vis", "account_type": "Secondary", "alliance": "TNO"},
            {"account_name": "Vis kid", "account_type": "Farm", "alliance": "R&S"},
            {"account_name": "Eviseration", "account_type": "Main", "alliance": "R&S"},
        ],
    )

    create_user(client, "AnotherUser")
    login_user(client, "AnotherUser")
    save_user_info(client, "Other")
    user_store.save_accounts(
        "AnotherUser",
        [{"account_name": "Quiet Farm", "account_type": "Farm", "alliance": "TON"}],
    )

    login_user(client, "Eviseration")
    response = client.get("/alliance-users?search=Vis+kid")
    content = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="search"' in content
    search_index = content.index('name="search"')
    account_type_filter_index = content.index('name="account_type"')
    alliance_filter_index = content.index('name="alliance"')
    assert search_index < account_type_filter_index < alliance_filter_index
    assert "Eviseration | Aaron" in content
    assert "<th>Main</th>" in content
    assert "<th>Secondary</th>" in content
    assert "<th>Farm1</th>" in content
    assert "<th>Farm2</th>" in content
    main_index = content.index("Eviseration (R&amp;S)")
    secondary_index = content.index("The Vis (TNO)")
    baby_farm_index = content.index("Baby Vis Doot Doot (R&amp;S)")
    vis_kid_index = content.index("Vis kid (R&amp;S)")
    assert main_index < secondary_index < baby_farm_index < vis_kid_index
    assert "AnotherUser | Other" not in content

    filtered = client.get("/alliance-users?search=Vis+kid&account_type=Farm&alliance=TNO")
    assert "No users matched the current search and filters." in filtered.get_data(as_text=True)
