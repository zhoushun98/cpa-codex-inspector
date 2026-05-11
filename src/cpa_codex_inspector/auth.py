from __future__ import annotations

import base64
import json
from typing import Any

from .models import AuthAccount


def normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)):
        return str(value)
    return None


def normalize_auth_index(value: Any) -> str | None:
    return normalize_string(value)


def _read_nested_record(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    return None


def _decode_base64url(segment: str) -> str | None:
    try:
        normalized = segment.replace("-", "+").replace("_", "/")
        padded = normalized + ("=" * ((4 - len(normalized) % 4) % 4))
        return base64.b64decode(padded).decode("utf-8")
    except Exception:
        return None


def parse_id_token_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    token = value.strip()
    if not token:
        return None
    try:
        parsed = json.loads(token)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    parts = token.split(".")
    if len(parts) < 2:
        return None
    decoded = _decode_base64url(parts[1])
    if not decoded:
        return None
    try:
        parsed = json.loads(decoded)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _resolve_account_id_candidate(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return normalize_string(
        value.get("chatgpt_account_id")
        or value.get("chatgptAccountId")
        or value.get("account_id")
        or value.get("accountId")
    )


def extract_codex_chatgpt_account_id(value: Any) -> str | None:
    direct = _resolve_account_id_candidate(value)
    if direct:
        return direct
    payload = parse_id_token_payload(value)
    if not payload:
        return None
    return _resolve_account_id_candidate(payload)


def resolve_codex_chatgpt_account_id(file: dict[str, Any]) -> str | None:
    metadata = _read_nested_record(file.get("metadata"))
    attributes = _read_nested_record(file.get("attributes"))
    candidates = [
        file.get("chatgpt_account_id"),
        file.get("chatgptAccountId"),
        file.get("account_id"),
        file.get("accountId"),
        metadata.get("chatgpt_account_id") if metadata else None,
        metadata.get("chatgptAccountId") if metadata else None,
        metadata.get("account_id") if metadata else None,
        metadata.get("accountId") if metadata else None,
        attributes.get("chatgpt_account_id") if attributes else None,
        attributes.get("chatgptAccountId") if attributes else None,
        attributes.get("account_id") if attributes else None,
        attributes.get("accountId") if attributes else None,
        file.get("id_token"),
        metadata.get("id_token") if metadata else None,
        attributes.get("id_token") if attributes else None,
    ]
    for candidate in candidates:
        account_id = extract_codex_chatgpt_account_id(candidate)
        if account_id:
            return account_id
    return None


def is_disabled_auth_file(file: dict[str, Any]) -> bool:
    value = file.get("disabled")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    status = normalize_string(file.get("status")) or ""
    return status.lower() == "disabled"


def resolve_auth_provider(file: dict[str, Any]) -> str:
    provider = normalize_string(file.get("provider") or file.get("type"))
    return provider.lower() if provider else ""


def read_file_name(file: dict[str, Any]) -> str:
    for key in ("name", "id"):
        value = normalize_string(file.get(key))
        if value:
            return value
    auth_index = normalize_auth_index(file.get("auth_index") or file.get("authIndex"))
    return auth_index or "unknown-auth-file"


def read_display_account(file: dict[str, Any]) -> str:
    for key in ("account", "email", "label", "name", "id"):
        value = normalize_string(file.get(key))
        if value:
            return value
    return normalize_auth_index(file.get("auth_index") or file.get("authIndex")) or "-"


def to_auth_account(file: dict[str, Any]) -> AuthAccount:
    file_name = read_file_name(file)
    auth_index = normalize_auth_index(file.get("auth_index") or file.get("authIndex"))
    return AuthAccount(
        key=f"{file_name}::{auth_index or '-'}",
        file_name=file_name,
        display_account=read_display_account(file),
        auth_index=auth_index,
        account_id=resolve_codex_chatgpt_account_id(file),
        provider=resolve_auth_provider(file),
        disabled=is_disabled_auth_file(file),
        status=normalize_string(file.get("status")) or "",
        state=normalize_string(file.get("state")) or "",
        raw=file,
    )

