from __future__ import annotations

import base64
import json

from cpa_codex_inspector.auth import parse_id_token_payload, to_auth_account


def _jwt_payload(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"header.{encoded}.signature"


def test_parse_id_token_payload_reads_json_and_jwt() -> None:
    assert parse_id_token_payload('{"chatgpt_account_id":"acc-json"}') == {"chatgpt_account_id": "acc-json"}
    assert parse_id_token_payload(_jwt_payload({"chatgpt_account_id": "acc-jwt"})) == {
        "chatgpt_account_id": "acc-jwt"
    }


def test_to_auth_account_normalizes_codex_file() -> None:
    account = to_auth_account(
        {
            "name": "codex-001.json",
            "provider": "CoDeX",
            "email": "user@example.com",
            "auth_index": 7,
            "disabled": "true",
            "metadata": {"id_token": _jwt_payload({"chatgpt_account_id": "chatgpt-account"})},
        }
    )

    assert account.file_name == "codex-001.json"
    assert account.display_account == "user@example.com"
    assert account.auth_index == "7"
    assert account.provider == "codex"
    assert account.disabled is True
    assert account.account_id == "chatgpt-account"
