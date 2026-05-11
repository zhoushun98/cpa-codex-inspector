from __future__ import annotations

import json
from typing import Any

from .models import Action, AuthAccount, InspectionResult

CODEX_USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
QUOTA_BODY_PATTERNS = ("quota exhausted", "limit reached", "payment_required")
FIVE_HOUR_WINDOW_SECONDS = 18_000
WEEK_WINDOW_SECONDS = 604_800


def parse_usage_payload(payload: Any) -> dict[str, Any] | None:
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        stripped = payload.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def normalize_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value == value:
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.endswith("%"):
            stripped = stripped[:-1]
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def get_rate_limit(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    value = payload.get("rate_limit") or payload.get("rateLimit")
    return value if isinstance(value, dict) else None


def _window_used_percent(window: dict[str, Any] | None) -> float | None:
    if not window:
        return None
    return normalize_number(window.get("used_percent") or window.get("usedPercent"))


def _window_seconds(window: dict[str, Any] | None) -> float | None:
    if not window:
        return None
    return normalize_number(window.get("limit_window_seconds") or window.get("limitWindowSeconds"))


def _limit_windows(rate_limit: dict[str, Any] | None) -> list[dict[str, Any] | None]:
    if not rate_limit:
        return []
    primary = rate_limit.get("primary_window") or rate_limit.get("primaryWindow")
    secondary = rate_limit.get("secondary_window") or rate_limit.get("secondaryWindow")
    return [
        primary if isinstance(primary, dict) else None,
        secondary if isinstance(secondary, dict) else None,
    ]


def derive_used_percent(rate_limit: dict[str, Any] | None) -> float | None:
    values = [_window_used_percent(window) for window in _limit_windows(rate_limit)]
    real_values = [value for value in values if value is not None]
    return max(real_values) if real_values else None


def is_rate_limit_reached(rate_limit: dict[str, Any] | None) -> bool:
    if not rate_limit:
        return False
    if rate_limit.get("allowed") is False:
        return True
    if rate_limit.get("limit_reached") is True or rate_limit.get("limitReached") is True:
        return True
    return any(
        used is not None and used >= 100
        for used in (_window_used_percent(window) for window in _limit_windows(rate_limit))
    )


def pick_classified_windows(
    rate_limit: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    windows = _limit_windows(rate_limit)
    primary = windows[0] if windows else None
    secondary = windows[1] if len(windows) > 1 else None
    five_hour = None
    weekly = None
    for window in windows:
        seconds = _window_seconds(window)
        if seconds == FIVE_HOUR_WINDOW_SECONDS and five_hour is None:
            five_hour = window
        elif seconds == WEEK_WINDOW_SECONDS and weekly is None:
            weekly = window
    if five_hour is None and primary is not weekly:
        five_hour = primary
    if weekly is None and secondary is not five_hour:
        weekly = secondary
    return five_hour, weekly


def _decision(
    account: AuthAccount,
    action: Action,
    reason: str,
    status_code: int | None,
    used_percent: float | None,
    is_quota: bool,
    error: str = "",
) -> InspectionResult:
    return InspectionResult(
        account=account,
        action=action,
        action_reason=reason,
        status_code=status_code,
        used_percent=used_percent,
        is_quota=is_quota,
        error=error,
    )


def resolve_probe_action(
    account: AuthAccount,
    status_code: int,
    body_text: str,
    payload: dict[str, Any] | None,
    threshold: float,
    *,
    disable_five_hour_exhausted: bool = False,
) -> InspectionResult:
    rate_limit = get_rate_limit(payload)
    used_percent = derive_used_percent(rate_limit)
    body_lower = body_text.lower()
    is_quota = (
        status_code == 402
        or any(pattern in body_lower for pattern in QUOTA_BODY_PATTERNS)
        or is_rate_limit_reached(rate_limit)
        or (used_percent is not None and used_percent >= threshold)
    )

    five_hour_window, weekly_window = pick_classified_windows(rate_limit)
    weekly_used = _window_used_percent(weekly_window)
    if weekly_window is not None and weekly_used is not None:
        five_hour_used = _window_used_percent(five_hour_window)
        weekly_over = weekly_used >= threshold
        five_hour_over = five_hour_used is not None and five_hour_used >= threshold

        if status_code == 401:
            return _decision(account, "delete", "接口返回 401，建议删除失效账号", status_code, weekly_used, False)
        if weekly_over:
            if account.disabled:
                return _decision(account, "keep", "周额度达到阈值，但账号已禁用", status_code, weekly_used, True)
            return _decision(account, "disable", "周额度达到阈值，建议禁用账号", status_code, weekly_used, True)
        if five_hour_over and disable_five_hour_exhausted:
            if account.disabled:
                return _decision(
                    account,
                    "keep",
                    "5 小时额度达到阈值，账号已禁用，等待短周期额度恢复",
                    status_code,
                    weekly_used,
                    True,
                )
            return _decision(
                account,
                "disable",
                "5 小时额度达到阈值，周额度仍可用，按配置建议临时禁用账号",
                status_code,
                weekly_used,
                True,
            )
        if account.disabled:
            return _decision(account, "enable", "5 小时额度和周额度均可用，建议重新启用账号", status_code, weekly_used, False)
        if five_hour_over:
            return _decision(account, "keep", "5 小时额度达到阈值，但周额度仍可用，暂不禁用账号", status_code, weekly_used, False)
        return _decision(account, "keep", "周额度仍可用，无需处理", status_code, weekly_used, False)

    if status_code == 401:
        return _decision(account, "delete", "接口返回 401，建议删除失效账号", status_code, used_percent, False)
    if is_quota:
        if account.disabled:
            return _decision(account, "keep", "额度已耗尽或超阈值，但账号已禁用", status_code, used_percent, True)
        return _decision(account, "disable", "额度已耗尽或超阈值，建议禁用账号", status_code, used_percent, True)
    if status_code == 200 and account.disabled:
        return _decision(account, "enable", "账号恢复健康，建议重新启用", status_code, used_percent, False)
    return _decision(account, "keep", "无需处理", status_code, used_percent, False)
