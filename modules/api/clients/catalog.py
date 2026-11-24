"""REST client for the CAPS sandbox (successor of the 2023 ``GitHub`` client).

Differences from the historical client: one ``requests.Session`` (cookie jar = one login), bounded
``(connect, read)`` timeouts on every call, typed failures, quoted path segments, and no assumption that a
body is JSON. ``request`` returns the raw status/body so that tests can assert negative statuses; the
convenience methods raise ``ApiHttpError`` for non-2xx answers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

from modules.api.clients.errors import ApiConnectionError, ApiHttpError, ApiMalformedResponse, ApiTimeout
from modules.config import DEFAULT, Settings


@dataclass
class ApiResponse:
    status: int
    headers: Dict[str, str]
    body: Any
    text: str

    @property
    def error_code(self) -> Optional[str]:
        if isinstance(self.body, dict) and isinstance(self.body.get("error"), dict):
            return self.body["error"].get("code")
        return None


class CatalogClient:
    def __init__(self, base_url: str, settings: Settings = DEFAULT):
        self.base_url = base_url.rstrip("/")
        self.settings = settings
        self._session = requests.Session()

    # -- lifecycle ---------------------------------------------------------------------------------
    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> "CatalogClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def cookies(self) -> Dict[str, str]:
        return self._session.cookies.get_dict()

    def set_cookie(self, name: str, value: str) -> None:
        self._session.cookies.set(name, value, domain="127.0.0.1", path="/")

    # -- low level ---------------------------------------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        json_body: Any = None,
        raw_body: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        expect_json: bool = True,
    ) -> ApiResponse:
        read_timeout = self.settings.read_timeout if timeout is None else timeout
        kwargs: Dict[str, Any] = {
            "params": params,
            "timeout": (self.settings.connect_timeout, read_timeout),
            "allow_redirects": False,
        }
        if raw_body is not None:
            kwargs["data"] = raw_body.encode("utf-8")
            kwargs["headers"] = {"Content-Type": "application/json"}
        elif json_body is not None:
            kwargs["json"] = json_body
        try:
            resp = self._session.request(method, self.base_url + path, **kwargs)
        except requests.exceptions.Timeout as exc:
            raise ApiTimeout("%s %s timed out after %.2f s" % (method, path, read_timeout)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise ApiConnectionError("%s %s could not connect: %s" % (method, path, type(exc).__name__)) from exc
        body: Any = None
        if resp.content and (expect_json or resp.status_code >= 400):
            try:
                body = resp.json()
            except ValueError as exc:
                if expect_json:
                    raise ApiMalformedResponse("response body is not valid JSON", resp.text[:200]) from exc
        return ApiResponse(resp.status_code, dict(resp.headers), body, resp.text)

    def _ok(self, resp: ApiResponse, expected: int = 200) -> ApiResponse:
        """Return ``resp`` if the status is the expected one, else raise ``ApiHttpError`` (never anything else).

        The frozen error envelope is ``{"error": {"code": str, "message": str}}``. If the body does not have
        that shape (a plain string, a list, ``{"error": "text"}``, wrong field types) the failure is still an
        ``ApiHttpError`` carrying the real status, with ``code=None``, ``envelope_valid=False`` and the raw
        body in ``payload``; the unreadable envelope is never trusted or parsed further.
        """
        if resp.status != expected:
            code, message = _read_error_envelope(resp.body)
            raise ApiHttpError(resp.status, code, message if code is not None else _BAD_ENVELOPE, resp.body,
                               envelope_valid=code is not None)
        return resp

    def _object(self, resp: ApiResponse, key: Optional[str] = None) -> Any:
        if not isinstance(resp.body, dict) or (key is not None and key not in resp.body):
            raise ApiMalformedResponse("unexpected response shape", resp.text[:200])
        return resp.body[key] if key else resp.body

    def _checked(self, resp: ApiResponse, check: Callable[[Any], None], key: Optional[str] = None) -> Any:
        """Extract ``key`` (or the whole object) and run a shape check; failures are ``ApiMalformedResponse``."""
        value = self._object(resp, key)
        try:
            check(value)
        except ValueError as exc:
            raise ApiMalformedResponse("response does not match the contract: %s" % exc, resp.text[:200]) from exc
        return value

    # -- contract operations (every body is shape-checked; ``request()`` stays raw on purpose) -----
    def health(self) -> Dict[str, Any]:
        return self._checked(self._ok(self.request("GET", "/api/v1/health")), _check_health)  # type: ignore[no-any-return]

    def login(self, username: str, password: str) -> Dict[str, Any]:
        resp = self._ok(self.request("POST", "/api/v1/session", {"username": username, "password": password}))
        return self._checked(resp, _check_user, "user")  # type: ignore[no-any-return]

    def whoami(self) -> Dict[str, Any]:
        return self._checked(self._ok(self.request("GET", "/api/v1/session")), _check_user, "user")  # type: ignore[no-any-return]

    def logout(self) -> None:
        self._ok(self.request("DELETE", "/api/v1/session", expect_json=False), 204)

    def list_items(self, q: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {"q": q} if q is not None else None
        resp = self._ok(self.request("GET", "/api/v1/items", params=params))
        self._checked(resp, _check_item_list)  # the whole envelope: items, count and their consistency
        return resp.body["items"]  # type: ignore[no-any-return]

    def get_item(self, sku: str) -> Dict[str, Any]:
        return self._checked(self._ok(self.request("GET", "/api/v1/items/" + quote(sku, safe=""))), _check_item)  # type: ignore[no-any-return]

    def create_item(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._checked(self._ok(self.request("POST", "/api/v1/items", payload), 201), _check_item)  # type: ignore[no-any-return]

    def edit_item(self, sku: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._ok(self.request("PATCH", "/api/v1/items/" + quote(sku, safe=""), payload))
        return self._checked(resp, _check_item)  # type: ignore[no-any-return]

    def publish_item(self, sku: str) -> Dict[str, Any]:
        resp = self._ok(self.request("POST", "/api/v1/items/" + quote(sku, safe="") + "/publish"))
        return self._checked(resp, _check_item)  # type: ignore[no-any-return]


# -- response shape checks (contract sections 4 and 5); each raises ValueError with a short reason ------------
_BAD_ENVELOPE = "error response does not have the documented {error: {code, message}} shape"
_ITEM_KEYS = {"sku": str, "name": str, "description": str, "quantity": int, "state": str}
_STATES = ("DRAFT", "PUBLISHED")
_ROLES = ("viewer", "editor", "publisher")


def _read_error_envelope(body: Any) -> Tuple[Optional[str], str]:
    """Return (code, message) from a well-formed error envelope, else (None, "")."""
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        err = body["error"]
        if isinstance(err.get("code"), str) and isinstance(err.get("message"), str):
            return err["code"], err["message"]
    return None, ""


def _check_fields(value: Any, spec: Dict[str, type], what: str) -> None:
    if not isinstance(value, dict):
        raise ValueError("%s must be an object" % what)
    if set(value) != set(spec):
        raise ValueError("%s must have exactly the fields %s" % (what, sorted(spec)))
    for name, expected in spec.items():
        item = value[name]
        if isinstance(item, bool) or not isinstance(item, expected):  # bool is never an int/str here
            raise ValueError("%s.%s must be %s" % (what, name, expected.__name__))


def _check_item(value: Any) -> None:
    _check_fields(value, _ITEM_KEYS, "item")
    if value["state"] not in _STATES:
        raise ValueError("item.state must be one of %s" % (_STATES,))


def _check_user(value: Any) -> None:
    _check_fields(value, {"username": str, "role": str}, "user")
    if value["role"] not in _ROLES:
        raise ValueError("user.role must be one of %s" % (_ROLES,))


def _check_health(value: Any) -> None:
    _check_fields(value, {"status": str}, "health")


def _check_item_list(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != {"items", "count"}:
        raise ValueError("list response must be an object with exactly 'items' and 'count'")
    items, count = value["items"], value["count"]
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    if isinstance(count, bool) or not isinstance(count, int) or count != len(items):
        raise ValueError("count must be an integer equal to the number of items")
    for index, item in enumerate(items):
        try:
            _check_item(item)
        except ValueError as exc:
            raise ValueError("items[%d]: %s" % (index, exc)) from exc
