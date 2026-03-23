"""Security-focused redirect tests."""

from __future__ import annotations

from tests.test_app import extract_csrf_token


def test_language_preference_rejects_protocol_relative_redirects(client) -> None:
    page = client.get("/")
    csrf_token = extract_csrf_token(page.get_data(as_text=True))

    response = client.post(
        "/preferences/language",
        data={
            "language": "fr",
            "csrf_token": csrf_token,
            "next_path": "//attacker.example/path",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_language_preference_cookie_uses_allowlisted_language_values(client) -> None:
    page = client.get("/")
    csrf_token = extract_csrf_token(page.get_data(as_text=True))

    response = client.post(
        "/preferences/language",
        data={
            "language": "fr\r\nSet-Cookie: attacker=1",
            "csrf_token": csrf_token,
            "next_path": "/",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "tno_language=en" in response.headers["Set-Cookie"]
