"""Flask application factory for the CAPS sandbox. See docs/API_CONTRACT.md for the frozen contract."""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
from typing import Any, Dict, Optional

from flask import Flask, Response, g, jsonify, redirect, render_template, request
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.wrappers import Response as WerkzeugResponse

from sandbox import policy, store, validation

COOKIE = "kqa_sid"
_DUMMY_HASH = generate_password_hash("not-a-real-password", method="pbkdf2:sha256:1000")
_QUERY_KEYS = {"q"}
_SKU_PATH_RE = validation.SKU_RE


def create_app(db_path: str, test_routes: bool = False) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path
    app.config["STOP_EVENT"] = threading.Event()
    app.json.sort_keys = False  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ plumbing
    def db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = store.connect(app.config["DB_PATH"])
        return g.db  # type: ignore[no-any-return]

    @app.teardown_appcontext
    def close_db(_exc: Optional[BaseException]) -> None:
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.after_request
    def api_headers(resp: Response) -> Response:
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    def current_user() -> Optional[sqlite3.Row]:
        return store.user_for_token(db(), request.cookies.get(COOKIE))

    def api_error(status: int, code: str, message: str, fields: Optional[list] = None) -> Response:
        body: Dict[str, Any] = {"error": {"code": code, "message": message}}
        if fields:
            body["error"]["fields"] = fields
        resp = jsonify(body)
        resp.status_code = status
        return resp

    def unauthenticated() -> Response:
        return api_error(401, "unauthenticated", "Authentication is required.")

    def forbidden() -> Response:
        return api_error(403, "forbidden", "Your role is not permitted to do this.")

    def not_found() -> Response:
        return api_error(404, "not_found", "Not found.")

    def read_json_object(allow_empty: bool = False) -> Any:
        """Return the JSON object body, or a Response describing why it is invalid.

        The declared Content-Type is intentionally NOT checked: the body is parsed as JSON whatever media type
        the client states (see docs/API_CONTRACT.md section 3). It is a test target, not a hardened service.
        """
        raw = request.get_data()
        if allow_empty and not raw.strip():
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return api_error(400, "invalid_json", "The request body is not valid JSON.")
        if not isinstance(data, dict):
            return api_error(400, "invalid_json", "The request body must be a JSON object.")
        return data

    def invalid_fields(errors: list) -> Response:
        return api_error(400, "invalid_request", "The request is invalid.", errors)

    def visible_item(user: sqlite3.Row, sku: str) -> Optional[Dict[str, Any]]:
        if not _SKU_PATH_RE.fullmatch(sku):
            return None
        item = store.get_item(db(), sku)
        if item is None:
            return None
        if item["state"] == "DRAFT" and not policy.can_read_drafts(user["role"]):
            return None
        return item

    # ------------------------------------------------------------------ REST: health and session
    @app.get("/api/v1/health")
    def api_health() -> Response:
        return jsonify({"status": "ok"})

    @app.post("/api/v1/session")
    def api_login() -> Response:
        data = read_json_object()
        if isinstance(data, Response):
            return data
        errors = []
        for key in data:
            if key not in ("username", "password"):
                errors.append({"field": key, "code": "unknown_field"})
        for key, limit in (("username", 64), ("password", 128)):
            value = data.get(key)
            if key not in data:
                errors.append({"field": key, "code": "required"})
            elif not isinstance(value, str):
                errors.append({"field": key, "code": "wrong_type"})
            elif not value:
                errors.append({"field": key, "code": "empty"})
            elif len(value) > limit:
                errors.append({"field": key, "code": "too_long"})
        if errors:
            return invalid_fields(errors)
        user = store.find_user(db(), data["username"])
        if user is None:
            check_password_hash(_DUMMY_HASH, data["password"])  # keep timing similar
            return api_error(401, "invalid_credentials", "Invalid username or password.")
        if not check_password_hash(user["password_hash"], data["password"]):
            return api_error(401, "invalid_credentials", "Invalid username or password.")
        token = secrets.token_urlsafe(32)
        store.create_session(db(), token, user["id"])
        resp = jsonify({"user": {"username": user["username"], "role": user["role"]}})
        resp.set_cookie(COOKIE, token, httponly=True, samesite="Lax", path="/")
        return resp

    @app.get("/api/v1/session")
    def api_whoami() -> Response:
        user = current_user()
        if user is None:
            return unauthenticated()
        return jsonify({"user": {"username": user["username"], "role": user["role"]}})

    @app.delete("/api/v1/session")
    def api_logout() -> Response:
        user = current_user()
        if user is None:
            return unauthenticated()
        store.delete_session(db(), request.cookies[COOKIE])
        resp = Response(status=204)
        resp.delete_cookie(COOKIE, path="/")
        return resp

    # ------------------------------------------------------------------ REST: items
    @app.get("/api/v1/items")
    def api_list_items() -> Response:
        user = current_user()
        if user is None:
            return unauthenticated()
        errors = [{"field": k, "code": "unknown_field"} for k in request.args if k not in _QUERY_KEYS]
        query = request.args.get("q")
        if query is not None and not (1 <= len(query.strip()) <= 80):
            errors.append({"field": "q", "code": "empty" if not query.strip() else "too_long"})
        if errors:
            return invalid_fields(errors)
        include_drafts = policy.can_read_drafts(user["role"])
        items = store.list_items(db(), include_drafts, query.strip() if query is not None else None)
        return jsonify({"items": items, "count": len(items)})

    @app.get("/api/v1/items/<sku>")
    def api_get_item(sku: str) -> Response:
        user = current_user()
        if user is None:
            return unauthenticated()
        item = visible_item(user, sku)
        if item is None:
            return not_found()
        return jsonify(item)

    @app.post("/api/v1/items")
    def api_create_item() -> Response:
        user = current_user()
        if user is None:
            return unauthenticated()
        if user["role"] not in policy.CREATE_ROLES:
            return forbidden()
        data = read_json_object()
        if isinstance(data, Response):
            return data
        clean, errors = validation.validate_item(data, "create")
        if errors:
            return invalid_fields(errors)
        try:
            store.insert_draft(db(), clean)
        except sqlite3.IntegrityError:
            return api_error(409, "duplicate_sku", "An item with this SKU already exists.")
        item = store.get_item(db(), clean["sku"])
        resp = jsonify(item)
        resp.status_code = 201
        resp.headers["Location"] = "/api/v1/items/" + clean["sku"]
        return resp

    @app.patch("/api/v1/items/<sku>")
    def api_edit_item(sku: str) -> Response:
        user = current_user()
        if user is None:
            return unauthenticated()
        if user["role"] not in policy.EDIT_ROLES:
            return forbidden()
        data = read_json_object()
        if isinstance(data, Response):
            return data
        clean, errors = validation.validate_item(data, "edit")
        if errors:
            return invalid_fields(errors)
        item = visible_item(user, sku)
        if item is None:
            return not_found()
        if item["state"] == "PUBLISHED":
            return api_error(409, "item_published", "Published items cannot be modified.")
        store.update_item(db(), sku, clean)
        return jsonify(store.get_item(db(), sku))

    @app.post("/api/v1/items/<sku>/publish")
    def api_publish_item(sku: str) -> Response:
        user = current_user()
        if user is None:
            return unauthenticated()
        if user["role"] not in policy.PUBLISH_ROLES:
            return forbidden()
        data = read_json_object(allow_empty=True)
        if isinstance(data, Response):
            return data
        if data:
            return invalid_fields([{"field": k, "code": "unknown_field"} for k in data])
        item = visible_item(user, sku)
        if item is None:
            return not_found()
        if item["state"] == "PUBLISHED":
            return api_error(409, "already_published", "The item is already published.")
        store.publish_item(db(), sku)
        return jsonify(store.get_item(db(), sku))

    @app.errorhandler(404)
    def handle_404(_e: Exception) -> Any:
        if request.path.startswith("/api/"):
            return not_found()
        return render_template("error.html", title="Not found", message="The page does not exist."), 404

    @app.errorhandler(405)
    def handle_405(_e: Exception) -> Any:
        if request.path.startswith("/api/"):
            return api_error(405, "method_not_allowed", "Method not allowed.")
        return render_template("error.html", title="Not allowed", message="Method not allowed."), 405

    # ------------------------------------------------------------------ HTML UI
    def page(template: str, status: int = 200, **context: Any) -> Any:
        user = current_user()
        token = request.cookies.get(COOKIE)
        flash = store.pop_flash(db(), token) if (user is not None and token) else None
        return render_template(template, user=user, flash=flash, **context), status

    def error_page(status: int, title: str, message: str) -> Any:
        return page("error.html", status, title=title, message=message)

    def to_login() -> WerkzeugResponse:
        return redirect("/login", code=302)

    def flash_and_redirect(message: str, location: str) -> WerkzeugResponse:
        store.set_flash(db(), request.cookies[COOKIE], message)
        return redirect(location, code=303)

    @app.get("/")
    def ui_root() -> WerkzeugResponse:
        return redirect("/catalog", code=302)

    @app.get("/login")
    def ui_login_form() -> Any:
        return page("login.html", error=None, signed_out=request.args.get("signed_out") == "1")

    @app.post("/login")
    def ui_login_submit() -> Any:
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = store.find_user(db(), username) if username else None
        if user is None or not check_password_hash(user["password_hash"], password):
            return page("login.html", 401, error="Invalid username or password.", signed_out=False)
        token = secrets.token_urlsafe(32)
        store.create_session(db(), token, user["id"])
        resp = redirect("/catalog", code=303)
        resp.set_cookie(COOKIE, token, httponly=True, samesite="Lax", path="/")
        return resp

    @app.post("/logout")
    def ui_logout() -> WerkzeugResponse:
        if current_user() is not None:
            store.delete_session(db(), request.cookies[COOKIE])
        resp = redirect("/login?signed_out=1", code=303)
        resp.delete_cookie(COOKIE, path="/")
        return resp

    @app.get("/catalog")
    def ui_catalog() -> Any:
        user = current_user()
        if user is None:
            return to_login()
        items = store.list_items(db(), policy.can_read_drafts(user["role"]), None)
        return page("catalog.html", items=items, can_create=user["role"] in policy.CREATE_ROLES)

    @app.get("/items/new")
    def ui_new_form() -> Any:
        user = current_user()
        if user is None:
            return to_login()
        if user["role"] not in policy.CREATE_ROLES:
            return error_page(403, "Forbidden", "You do not have permission to do that.")
        return page("item_form.html", values={}, errors=[])

    def form_payload(include_sku: bool) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        fields = ("sku", "name", "description", "quantity") if include_sku else ("name", "description", "quantity")
        for field in fields:
            if field in request.form:
                payload[field] = request.form[field]
        raw_quantity = payload.get("quantity")
        if isinstance(raw_quantity, str):
            if raw_quantity.strip() == "":
                del payload["quantity"]
            elif re.fullmatch(r"-?\d{1,12}", raw_quantity.strip()):
                payload["quantity"] = int(raw_quantity.strip())
        return payload

    @app.post("/items/new")
    def ui_new_submit() -> Any:
        user = current_user()
        if user is None:
            return to_login()
        if user["role"] not in policy.CREATE_ROLES:
            return error_page(403, "Forbidden", "You do not have permission to do that.")
        payload = form_payload(include_sku=True)
        clean, errors = validation.validate_item(payload, "create")
        if errors:
            lines = [validation.describe(e) for e in errors]
            return page("item_form.html", 400, values=request.form, errors=lines)
        try:
            store.insert_draft(db(), clean)
        except sqlite3.IntegrityError:
            return page("item_form.html", 409, values=request.form, errors=["sku already exists"])
        return flash_and_redirect("Item %s created as DRAFT." % clean["sku"], "/items/" + clean["sku"])

    @app.get("/items/<sku>")
    def ui_item(sku: str) -> Any:
        user = current_user()
        if user is None:
            return to_login()
        item = visible_item(user, sku)
        if item is None:
            return error_page(404, "Not found", "The item does not exist.")
        return page(
            "item_detail.html",
            item=item,
            can_edit=user["role"] in policy.EDIT_ROLES and item["state"] == "DRAFT",
            can_publish=user["role"] in policy.PUBLISH_ROLES and item["state"] == "DRAFT",
            errors=[],
        )

    @app.post("/items/<sku>/edit")
    def ui_item_edit(sku: str) -> Any:
        user = current_user()
        if user is None:
            return to_login()
        if user["role"] not in policy.EDIT_ROLES:
            return error_page(403, "Forbidden", "You do not have permission to do that.")
        clean, errors = validation.validate_item(form_payload(include_sku=False), "edit")
        item = visible_item(user, sku)
        if errors:
            lines = [validation.describe(e) for e in errors]
            return page("item_detail.html", 400, item=item, can_edit=True, can_publish=False, errors=lines) if item \
                else error_page(404, "Not found", "The item does not exist.")
        if item is None:
            return error_page(404, "Not found", "The item does not exist.")
        if item["state"] == "PUBLISHED":
            return error_page(409, "Conflict", "Published items cannot be modified.")
        store.update_item(db(), sku, clean)
        return flash_and_redirect("Item %s updated." % sku, "/items/" + sku)

    @app.post("/items/<sku>/publish")
    def ui_item_publish(sku: str) -> Any:
        user = current_user()
        if user is None:
            return to_login()
        if user["role"] not in policy.PUBLISH_ROLES:
            return error_page(403, "Forbidden", "You do not have permission to do that.")
        item = visible_item(user, sku)
        if item is None:
            return error_page(404, "Not found", "The item does not exist.")
        if item["state"] == "PUBLISHED":
            return error_page(409, "Conflict", "The item is already published.")
        store.publish_item(db(), sku)
        return flash_and_redirect("Item %s published." % sku, "/items/" + sku)

    # ------------------------------------------------------------------ test-only routes (off by default)
    if test_routes:
        _register_test_routes(app)

    return app


def _register_test_routes(app: Flask) -> None:
    @app.get("/__test__/slow")
    def test_slow() -> Response:
        seconds = float(request.args.get("seconds", "5"))
        app.config["STOP_EVENT"].wait(timeout=seconds)  # released early when the server is stopped
        return jsonify({"status": "late"})

    @app.get("/__test__/malformed")
    def test_malformed() -> Response:
        return Response("{this is not json", status=200, mimetype="application/json")

    @app.get("/__test__/wrong-shape")
    def test_wrong_shape() -> Response:
        return Response("[1, 2, 3]", status=200, mimetype="application/json")

    @app.get("/__test__/error500")
    def test_error500() -> Response:
        resp = jsonify({"error": {"code": "internal_error", "message": "Simulated failure."}})
        resp.status_code = 500
        return resp
