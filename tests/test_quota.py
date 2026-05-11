from __future__ import annotations

from cpa_codex_inspector.models import AuthAccount
from cpa_codex_inspector.quota import resolve_probe_action


def _account(*, disabled: bool = False) -> AuthAccount:
    return AuthAccount(
        key="codex.json::1",
        file_name="codex.json",
        display_account="user@example.com",
        auth_index="1",
        account_id=None,
        provider="codex",
        disabled=disabled,
        status="disabled" if disabled else "enabled",
        state="",
        raw={},
    )


def _usage(five_hour: float, weekly: float, *, allowed: bool = True) -> dict:
    return {
        "rate_limit": {
            "allowed": allowed,
            "primary_window": {"limit_window_seconds": 18_000, "used_percent": five_hour},
            "secondary_window": {"limit_window_seconds": 604_800, "used_percent": weekly},
        }
    }


def test_401_is_delete() -> None:
    result = resolve_probe_action(_account(), 401, "", None, 100)

    assert result.action == "delete"
    assert result.is_quota is False


def test_weekly_over_threshold_disables_enabled_account() -> None:
    result = resolve_probe_action(_account(), 200, "", _usage(10, 100), 100)

    assert result.action == "disable"
    assert result.used_percent == 100
    assert result.is_quota is True


def test_disabled_account_with_available_weekly_quota_is_enabled() -> None:
    result = resolve_probe_action(_account(disabled=True), 200, "", _usage(100, 30), 100)

    assert result.action == "enable"
    assert result.is_quota is False


def test_five_hour_over_weekly_available_keeps_enabled_account() -> None:
    result = resolve_probe_action(_account(), 200, "", _usage(100, 30), 100)

    assert result.action == "keep"
    assert "5 小时" in result.action_reason


def test_five_hour_over_can_disable_enabled_account() -> None:
    result = resolve_probe_action(
        _account(),
        200,
        "",
        _usage(100, 30),
        100,
        disable_five_hour_exhausted=True,
    )

    assert result.action == "disable"
    assert result.is_quota is True
    assert "临时禁用" in result.action_reason


def test_five_hour_over_keeps_disabled_account_when_policy_enabled() -> None:
    result = resolve_probe_action(
        _account(disabled=True),
        200,
        "",
        _usage(100, 30),
        100,
        disable_five_hour_exhausted=True,
    )

    assert result.action == "keep"
    assert result.is_quota is True
    assert "等待短周期额度恢复" in result.action_reason


def test_disabled_account_is_enabled_after_five_hour_recovers_when_policy_enabled() -> None:
    result = resolve_probe_action(
        _account(disabled=True),
        200,
        "",
        _usage(20, 30),
        100,
        disable_five_hour_exhausted=True,
    )

    assert result.action == "enable"
    assert result.is_quota is False
    assert "均可用" in result.action_reason


def test_quota_body_pattern_disables_without_rate_limit_payload() -> None:
    result = resolve_probe_action(_account(), 402, "quota exhausted", None, 100)

    assert result.action == "disable"
    assert result.is_quota is True
