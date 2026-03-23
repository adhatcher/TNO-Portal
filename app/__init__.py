"""Flask application factory."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from flask import Flask, Response, flash, g, jsonify, make_response, redirect, render_template, request, session, url_for

from app.config import Config
from app.instrumentation import instrument, render_metrics
from app.security import get_csrf_token, hash_password, validate_csrf, validate_password, verify_password
from app.storage import DEFAULT_ALLIANCES, DEFAULT_ACCOUNT_TYPES, UserStore, create_user_store
from app.translations import LANGUAGE_NAMES, TRANSLATIONS

ACCOUNT_TYPE_SORT_ORDER = {"Main": 0, "Secondary": 1, "Farm": 2}


def create_app(config_class: type[Config] = Config) -> Flask:
    """Application factory."""

    app = Flask(__name__)
    app.config.from_object(config_class)
    configure_storage(app.config["APP_DATA_DIR"])
    app.config["USER_STORE"] = create_user_store(app.config)
    configure_logging(app)
    register_hooks(app)
    register_routes(app)
    return app


@instrument("configure_storage")
def configure_storage(data_dir: Path) -> None:
    """Ensure the data directory exists for external volumes."""

    data_dir.mkdir(parents=True, exist_ok=True)


@instrument("configure_logging")
def configure_logging(app: Flask) -> None:
    """Configure file-based application logging."""

    logger = logging.getLogger("tno")
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(app.config["LOG_PATH"], maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False


@instrument("register_hooks")
def register_hooks(app: Flask) -> None:
    """Register request hooks and template helpers."""

    user_store: UserStore = app.config["USER_STORE"]

    @app.before_request
    @instrument("load_request_context")
    def load_request_context() -> None:
        language = request.cookies.get(app.config["LANGUAGE_COOKIE_NAME"], "en")
        session_user = session.get("current_user")
        current_user = user_store.get_user(session_user) if session_user else None
        if current_user and current_user.get("preferred_language"):
            language = current_user["preferred_language"]
        if language not in app.config["SUPPORTED_LANGUAGES"]:
            language = "en"

        translations = dict(TRANSLATIONS["en"])
        translations.update(TRANSLATIONS.get(language, {}))

        g.language = language
        g.translations = translations
        g.csrf_token = get_csrf_token()
        g.current_user = current_user
        g.is_admin = bool(current_user and current_user.get("user_type") == "Admin")
        response_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": (
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; base-uri 'self'; form-action 'self'"
            ),
        }
        g.security_headers = response_headers

    @app.after_request
    @instrument("apply_security_headers")
    def apply_security_headers(response: Response) -> Response:
        for header_name, header_value in g.get("security_headers", {}).items():
            response.headers.setdefault(header_name, header_value)
        return response

    @app.context_processor
    @instrument("inject_template_context")
    def inject_template_context() -> dict[str, Any]:
        return {
            "t": g.get("translations", TRANSLATIONS["en"]),
            "language_names": LANGUAGE_NAMES,
            "current_language": g.get("language", "en"),
            "csrf_token": g.get("csrf_token", get_csrf_token()),
            "remembered_user": request.cookies.get(app.config["REMEMBER_COOKIE_NAME"], ""),
            "current_path": request.path,
            "current_user": g.get("current_user"),
            "is_admin": g.get("is_admin", False),
            "request_args": request.args,
        }


@instrument("register_routes")
def register_routes(app: Flask) -> None:
    """Register application routes."""

    user_store: UserStore = app.config["USER_STORE"]

    @app.get("/")
    @instrument("welcome")
    def welcome() -> str:
        remembered_user = request.cookies.get(app.config["REMEMBER_COOKIE_NAME"])
        return render_template("welcome.html", remembered_user=remembered_user)

    @app.route("/login", methods=["GET", "POST"])
    @instrument("login")
    def login() -> Response | str:
        if request.method == "POST":
            if not validate_csrf(request.form.get("csrf_token")):
                return make_response("Invalid CSRF token", 400)

            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = user_store.get_user(username)
            if not user or not verify_password(user["password_hash"], password):
                flash(g.translations["login_failed"], "error")
            else:
                session["current_user"] = user["username"]
                destination = determine_post_login_route(user_store, user)
                response = make_response(redirect(url_for(destination)))
                set_preference_cookies(app, response, user.get("preferred_language") or g.language, user["display_name"])
                flash(g.translations["sign_in_cta"], "success")
                return response
        return render_template("login.html")

    @app.post("/logout")
    @instrument("logout")
    def logout() -> Response:
        if not validate_csrf(request.form.get("csrf_token")):
            return make_response("Invalid CSRF token", 400)
        session.pop("current_user", None)
        response = make_response(redirect(url_for("welcome")))
        response.delete_cookie(app.config["REMEMBER_COOKIE_NAME"])
        return response

    @app.route("/create-account-access", methods=["GET", "POST"])
    @instrument("access_code")
    def access_code() -> Response | str:
        if request.method == "POST":
            if not validate_csrf(request.form.get("csrf_token")):
                return make_response("Invalid CSRF token", 400)
            access_code_value = request.form.get("access_code", "").strip().upper()
            if access_code_value == app.config["INVITE_CODE"]:
                session["invite_code_verified"] = True
                return redirect(url_for("create_account"))
            flash(g.translations["invalid_code"], "error")
        return render_template("access_code.html")

    @app.route("/create-account", methods=["GET", "POST"])
    @instrument("create_account")
    def create_account() -> Response | str:
        if not session.get("invite_code_verified"):
            return redirect(url_for("access_code"))

        if request.method == "POST":
            if not validate_csrf(request.form.get("csrf_token")):
                return make_response("Invalid CSRF token", 400)

            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not username:
                flash(g.translations["username_required"], "error")
            elif user_store.username_exists(username):
                flash(g.translations["taken"], "error")
            elif not validate_password(password) or password != confirm_password:
                flash(g.translations["password_false"], "error")
            else:
                user = user_store.create_user(username, hash_password(password))
                session.pop("invite_code_verified", None)
                session["current_user"] = user["username"]
                response = make_response(redirect(url_for("user_info")))
                set_preference_cookies(app, response, g.language, username)
                flash(g.translations["account_created"], "success")
                return response

        return render_template("create_account.html")

    @app.route("/user-info", methods=["GET", "POST"])
    @instrument("user_info")
    def user_info() -> Response | str:
        current_user = require_login(user_store)
        if isinstance(current_user, Response):
            return current_user

        accounts_exist = user_store.has_accounts(current_user["username"])
        if request.method == "POST":
            if not validate_csrf(request.form.get("csrf_token")):
                return make_response("Invalid CSRF token", 400)

            action = request.form.get("action", "save_info")
            if action == "save_info":
                first_name = request.form.get("first_name", "").strip()
                if not first_name:
                    flash(g.translations["first_name_required"], "error")
                else:
                    preferred_language = request.form.get("preferred_language", "").strip()
                    user_store.update_profile(
                        current_user["username"],
                        first_name,
                        request.form.get("last_name", ""),
                        request.form.get("email", ""),
                        preferred_language,
                    )
                    response = make_response(redirect(url_for("accounts")))
                    set_preference_cookies(
                        app,
                        response,
                        preferred_language or g.language,
                        current_user["display_name"],
                    )
                    flash(g.translations["user_info_saved"], "success")
                    return response
            elif action == "reset_password":
                new_password = request.form.get("new_password", "")
                confirm_password = request.form.get("confirm_new_password", "")
                if validate_password(new_password) and new_password == confirm_password:
                    user_store.update_password(current_user["username"], hash_password(new_password))
                    flash(g.translations["password_reset_success"], "success")
                    return redirect(url_for("user_info"))
                flash(g.translations["password_false"], "error")
            elif action == "delete_user":
                if accounts_exist:
                    flash(g.translations["delete_user_blocked"], "error")
                else:
                    user_store.delete_user(current_user["username"])
                    session.pop("current_user", None)
                    response = make_response(redirect(url_for("welcome")))
                    response.delete_cookie(app.config["REMEMBER_COOKIE_NAME"])
                    flash(g.translations["user_deleted"], "success")
                    return response

        refreshed_user = user_store.get_user(current_user["username"])
        return render_template(
            "user_info.html",
            profile_user=refreshed_user,
            delete_user_disabled=accounts_exist,
        )

    @app.route("/accounts", methods=["GET", "POST"])
    @instrument("accounts")
    def accounts() -> Response | str:
        current_user = require_login(user_store)
        if isinstance(current_user, Response):
            return current_user

        if not user_store.has_profile_data(current_user["username"]):
            return redirect(url_for("user_info"))

        account_types = user_store.get_options("account_types")
        alliances = user_store.get_options("alliances")
        accounts_data = user_store.get_accounts(current_user["username"])
        if not accounts_data:
            accounts_data = [build_default_account_row(current_user["display_name"], account_types, alliances)]

        if request.method == "POST":
            if not validate_csrf(request.form.get("csrf_token")):
                return make_response("Invalid CSRF token", 400)

            action = request.form.get("action", "save")
            accounts_data = parse_accounts_form(request)
            error_message = validate_accounts(accounts_data)
            if error_message:
                flash(g.translations[error_message], "error")
            else:
                if action == "delete":
                    selected_indexes = {int(index) for index in request.form.getlist("selected_rows")}
                    accounts_data = [row for index, row in enumerate(accounts_data) if index not in selected_indexes]
                    if not accounts_data:
                        accounts_data = [build_default_account_row(current_user["display_name"], account_types, alliances)]
                elif action == "add":
                    user_store.save_accounts(current_user["username"], accounts_data)
                    accounts_data.append(build_default_account_row("", account_types, alliances))
                    flash(g.translations["accounts_saved"], "success")
                    return render_template(
                        "accounts.html",
                        accounts=accounts_data,
                        account_types=account_types,
                        alliances=alliances,
                        accounts_user=current_user,
                    )

                user_store.save_accounts(current_user["username"], accounts_data)
                flash(g.translations["accounts_saved"], "success")
                return redirect(url_for("accounts"))

        return render_template(
            "accounts.html",
            accounts=accounts_data,
            account_types=account_types,
            alliances=alliances,
            accounts_user=current_user,
        )

    @app.get("/alliance-users")
    @instrument("alliance_users")
    def alliance_users() -> Response | str:
        current_user = require_login(user_store)
        if isinstance(current_user, Response):
            return current_user

        account_type_filter = request.args.get("account_type", "All")
        alliance_filter = request.args.get("alliance", "All")
        search_term = request.args.get("search", "").strip()
        users = filter_alliance_users(
            user_store.list_users(),
            account_type_filter,
            alliance_filter,
            search_term,
        )
        return render_template(
            "alliance_users.html",
            users=users,
            selected_account_type=account_type_filter,
            selected_alliance=alliance_filter,
            search_term=search_term,
        )

    @app.get("/admin")
    @instrument("admin_home")
    def admin_home() -> Response | str:
        admin_user = require_admin(user_store)
        if isinstance(admin_user, Response):
            return admin_user
        return render_template("admin.html")

    @app.route("/admin/account-types", methods=["GET", "POST"])
    @instrument("admin_account_types")
    def admin_account_types() -> Response | str:
        admin_user = require_admin(user_store)
        if isinstance(admin_user, Response):
            return admin_user
        return handle_option_maintenance(user_store, "account_types", "admin_account_types", "account_type")

    @app.route("/admin/alliances", methods=["GET", "POST"])
    @instrument("admin_alliances")
    def admin_alliances() -> Response | str:
        admin_user = require_admin(user_store)
        if isinstance(admin_user, Response):
            return admin_user
        return handle_option_maintenance(user_store, "alliances", "admin_alliances", "alliance")

    @app.route("/admin/users", methods=["GET", "POST"])
    @instrument("admin_users")
    def admin_users() -> Response | str:
        admin_user = require_admin(user_store)
        if isinstance(admin_user, Response):
            return admin_user

        if request.method == "POST":
            if not validate_csrf(request.form.get("csrf_token")):
                return make_response("Invalid CSRF token", 400)

            action = request.form.get("action", "save")
            usernames = request.form.getlist("username")
            user_types = request.form.getlist("user_type")
            if action == "delete":
                selected = set(request.form.getlist("selected_users"))
                for username in selected:
                    user_store.delete_user(username)
            else:
                for username, user_type in zip(usernames, user_types, strict=False):
                    user_store.update_user_type(username, user_type)
            flash(g.translations["admin_users_saved"], "success")
            return redirect(url_for("admin_users"))

        return render_template("admin_users.html", users=user_store.list_users())

    @app.get("/api/username-available")
    @instrument("username_available")
    def username_available() -> Response:
        username = request.args.get("username", "").strip()
        available = bool(username) and not user_store.username_exists(username)
        message_key = "available" if available else "taken"
        return jsonify({"available": available, "message": g.translations[message_key]})

    @app.post("/preferences/language")
    @instrument("set_language")
    def set_language() -> Response:
        if not validate_csrf(request.form.get("csrf_token")):
            return make_response("Invalid CSRF token", 400)

        language = request.form.get("language", "en")
        if language not in app.config["SUPPORTED_LANGUAGES"]:
            language = "en"
        current_user = g.get("current_user")
        if current_user:
            user_store.update_profile(
                current_user["username"],
                current_user.get("first_name", ""),
                current_user.get("last_name", ""),
                current_user.get("email", ""),
                language,
            )
        next_path = request.form.get("next_path", url_for("welcome"))
        if not next_path.startswith("/"):
            next_path = url_for("welcome")
        response = make_response(redirect(next_path))
        response.set_cookie(
            app.config["LANGUAGE_COOKIE_NAME"],
            language,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="Lax",
            secure=app.config["SESSION_COOKIE_SECURE"],
        )
        return response

    @app.get("/metrics")
    @instrument("metrics")
    def metrics() -> Response:
        return Response(render_metrics(), mimetype="text/plain; version=0.0.4")


@instrument("handle_option_maintenance")
def handle_option_maintenance(
    user_store: UserStore,
    category: str,
    route_name: str,
    entity_label: str,
) -> Response | str:
    """Handle CRUD for admin-managed option sets."""

    if request.method == "POST":
        if not validate_csrf(request.form.get("csrf_token")):
            return make_response("Invalid CSRF token", 400)
        action = request.form.get("action", "add")
        if action == "add":
            user_store.add_option(category, request.form.get("value", ""))
        elif action == "update":
            user_store.update_option(category, request.form.get("original_value", ""), request.form.get("value", ""))
        elif action == "delete":
            user_store.delete_option(category, request.form.get("original_value", ""))
        flash(g.translations["admin_options_saved"], "success")
        return redirect(url_for(route_name))

    items = user_store.get_options(category)
    template_name = "option_maintenance.html"
    return render_template(template_name, items=items, category=category, entity_label=entity_label)


@instrument("require_login")
def require_login(user_store: UserStore) -> dict[str, Any] | Response:
    """Return the logged-in user or redirect to login."""

    username = session.get("current_user")
    if not username:
        return redirect(url_for("login"))
    user = user_store.get_user(username)
    if not user:
        session.pop("current_user", None)
        return redirect(url_for("login"))
    return user


@instrument("require_admin")
def require_admin(user_store: UserStore) -> dict[str, Any] | Response:
    """Return the admin user or redirect to login."""

    user = require_login(user_store)
    if isinstance(user, Response):
        return user
    if user.get("user_type") != "Admin":
        flash(g.translations["admin_required"], "error")
        return redirect(url_for("accounts"))
    return user


@instrument("determine_post_login_route")
def determine_post_login_route(user_store: UserStore, user: dict[str, Any]) -> str:
    """Choose where a user lands after login."""

    if user_store.has_profile_data(user["username"]):
        return "accounts"
    return "user_info"


@instrument("build_default_account_row")
def build_default_account_row(
    display_name: str,
    account_types: list[str] | None = None,
    alliances: list[str] | None = None,
) -> dict[str, str]:
    """Return the default first account row."""

    resolved_account_types = account_types or DEFAULT_ACCOUNT_TYPES
    resolved_alliances = alliances or DEFAULT_ALLIANCES
    return {
        "account_name": display_name,
        "account_type": resolved_account_types[0],
        "alliance": resolved_alliances[0],
    }


@instrument("parse_accounts_form")
def parse_accounts_form(request_obj) -> list[dict[str, str]]:
    """Parse account table rows from a submitted form."""

    names = request_obj.form.getlist("account_name")
    types = request_obj.form.getlist("account_type")
    alliances = request_obj.form.getlist("alliance")
    rows = []
    for name, account_type, alliance in zip(names, types, alliances, strict=False):
        cleaned_name = name.strip()
        if not cleaned_name and not account_type and not alliance:
            continue
        rows.append(
            {
                "account_name": cleaned_name,
                "account_type": account_type,
                "alliance": alliance,
            }
        )
    return rows


@instrument("validate_accounts")
def validate_accounts(accounts: list[dict[str, str]]) -> str | None:
    """Validate account table rules."""

    if not accounts:
        return None
    if any(not account["account_name"] for account in accounts):
        return "account_name_required"
    if sum(1 for account in accounts if account["account_type"] == "Main") > 1:
        return "single_main_required"
    return None


@instrument("filter_alliance_users")
def filter_alliance_users(
    users: list[dict[str, Any]],
    account_type_filter: str,
    alliance_filter: str,
    search_term: str,
) -> list[dict[str, Any]]:
    """Return users and accounts matching alliance directory filters."""

    normalized_search = search_term.casefold()
    filtered_users = []
    for user in sorted(users, key=lambda item: item["username"]):
        accounts = sort_accounts(user.get("accounts", []))
        if normalized_search and not user_or_accounts_match(user, accounts, normalized_search):
            continue

        filtered_accounts = [
            account
            for account in accounts
            if (account_type_filter == "All" or account.get("account_type") == account_type_filter)
            and (alliance_filter == "All" or account.get("alliance") == alliance_filter)
        ]
        if filtered_accounts:
            filtered_users.append(
                {
                    "username": user["display_name"],
                    "first_name": user.get("first_name", ""),
                    "last_name": user.get("last_name", ""),
                    "email": user.get("email", ""),
                    "account_columns": build_account_columns(filtered_accounts),
                }
            )
    return filtered_users


@instrument("user_or_accounts_match")
def user_or_accounts_match(user: dict[str, Any], accounts: list[dict[str, str]], search_term: str) -> bool:
    """Return True when the user or any account matches the search term."""

    haystacks = [user.get("display_name", ""), user.get("username", "")]
    haystacks.extend(account.get("account_name", "") for account in accounts)
    return any(search_term in value.casefold() for value in haystacks)


@instrument("sort_accounts")
def sort_accounts(accounts: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sort accounts with Main first, then Secondary, then Farm."""

    return sorted(
        accounts,
        key=lambda account: (
            ACCOUNT_TYPE_SORT_ORDER.get(account.get("account_type", ""), 99),
            account.get("account_name", "").casefold(),
        ),
    )


@instrument("build_account_columns")
def build_account_columns(accounts: list[dict[str, str]]) -> list[dict[str, str]]:
    """Build display columns for the alliance user account table."""

    main_accounts = [account for account in accounts if account.get("account_type") == "Main"]
    secondary_accounts = [account for account in accounts if account.get("account_type") == "Secondary"]
    farm_accounts = [account for account in accounts if account.get("account_type") == "Farm"]

    columns = []
    if main_accounts:
        columns.append({"header": "Main", "value": format_account_display(main_accounts[0])})
    if secondary_accounts:
        columns.append({"header": "Secondary", "value": format_account_display(secondary_accounts[0])})
    for index, account in enumerate(farm_accounts, start=1):
        columns.append({"header": f"Farm{index}", "value": format_account_display(account)})
    return columns


@instrument("format_account_display")
def format_account_display(account: dict[str, str]) -> str:
    """Format account display text."""

    return f"{account.get('account_name', '')} ({account.get('alliance', '')})"


@instrument("set_preference_cookies")
def set_preference_cookies(app: Flask, response: Response, language: str, username: str) -> None:
    """Set persistent user preference cookies."""

    max_age = 60 * 60 * 24 * 365
    response.set_cookie(
        app.config["LANGUAGE_COOKIE_NAME"],
        language,
        max_age=max_age,
        httponly=True,
        samesite="Lax",
        secure=app.config["SESSION_COOKIE_SECURE"],
    )
    response.set_cookie(
        app.config["REMEMBER_COOKIE_NAME"],
        username,
        max_age=max_age,
        httponly=True,
        samesite="Lax",
        secure=app.config["SESSION_COOKIE_SECURE"],
    )
