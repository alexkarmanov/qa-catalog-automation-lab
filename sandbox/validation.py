"""Strict request validation for catalog items (contract section 4)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# Always use SKU_RE.fullmatch(): "$" would also accept a trailing newline ("SYN-X\n"), so the pattern is unanchored.
SKU_RE = re.compile(r"[A-Z0-9][A-Z0-9-]{1,31}")
MAX_QUANTITY = 1_000_000
MAX_NAME = 80
MAX_DESCRIPTION = 500

CREATE_FIELDS = ("sku", "name", "description", "quantity")
EDIT_FIELDS = ("name", "description", "quantity")

FIELD_MESSAGES = {
    "required": "is required",
    "wrong_type": "has the wrong type",
    "empty": "must not be empty",
    "too_long": "is too long",
    "out_of_range": "must be between 0 and 1000000",
    "bad_format": "has an invalid format",
    "unknown_field": "is not allowed",
    "immutable_field": "cannot be changed",
}

FieldError = Dict[str, str]


def _err(field: str, code: str) -> FieldError:
    return {"field": field, "code": code}


def validate_item(payload: Dict[str, Any], mode: str) -> Tuple[Dict[str, Any], List[FieldError]]:
    """Validate ``payload`` for ``mode`` in {"create", "edit"}; return (clean values, field errors)."""
    errors: List[FieldError] = []
    allowed = CREATE_FIELDS if mode == "create" else EDIT_FIELDS
    for key in payload:
        if key in allowed:
            continue
        if mode == "edit" and key == "sku":
            errors.append(_err(key, "immutable_field"))
        else:
            errors.append(_err(key, "unknown_field"))

    clean: Dict[str, Any] = {}

    if mode == "create":
        if "sku" not in payload:
            errors.append(_err("sku", "required"))
        elif not isinstance(payload["sku"], str):
            errors.append(_err("sku", "wrong_type"))
        elif not SKU_RE.fullmatch(payload["sku"]):
            errors.append(_err("sku", "bad_format"))
        else:
            clean["sku"] = payload["sku"]

    if "name" in payload:
        value = payload["name"]
        if not isinstance(value, str):
            errors.append(_err("name", "wrong_type"))
        elif not value.strip():
            errors.append(_err("name", "empty"))
        elif len(value.strip()) > MAX_NAME:
            errors.append(_err("name", "too_long"))
        else:
            clean["name"] = value.strip()
    elif mode == "create":
        errors.append(_err("name", "required"))

    if "description" in payload:
        value = payload["description"]
        if not isinstance(value, str):
            errors.append(_err("description", "wrong_type"))
        elif len(value.strip()) > MAX_DESCRIPTION:
            errors.append(_err("description", "too_long"))
        else:
            clean["description"] = value.strip()
    elif mode == "create":
        clean["description"] = ""

    if "quantity" in payload:
        value = payload["quantity"]
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(_err("quantity", "wrong_type"))
        elif value < 0 or value > MAX_QUANTITY:
            errors.append(_err("quantity", "out_of_range"))
        else:
            clean["quantity"] = value
    elif mode == "create":
        errors.append(_err("quantity", "required"))

    if mode == "edit" and not payload and not errors:
        errors.append(_err("body", "empty"))

    return clean, errors


def describe(error: FieldError) -> str:
    """Human-readable line used in HTML error lists, e.g. ``quantity must be between 0 and 1000000``."""
    return "%s %s" % (error["field"], FIELD_MESSAGES[error["code"]])
