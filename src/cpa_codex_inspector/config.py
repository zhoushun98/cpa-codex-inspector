from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .models import ActionConfig, AppConfig, CpaConfig, InspectConfig, OutputConfig

ENV_REF_PATTERN = re.compile(r"^\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))$")


class ConfigError(ValueError):
    """配置错误。"""


def _read_mapping(value: Any, key: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"`{key}` 必须是对象")
    return value


def _read_str(data: dict[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    text = str(value).strip()
    match = ENV_REF_PATTERN.match(text)
    if not match:
        return text
    env_name = match.group("braced") or match.group("plain") or ""
    return os.environ.get(env_name, "").strip()


def _read_int(data: dict[str, Any], key: str, default: int, *, minimum: int = 0) -> int:
    value = data.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _read_float(data: dict[str, Any], key: str, default: float, *, minimum: float = 0.0) -> float:
    value = data.get(key, default)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _read_bool(data: dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return default


def _normalize_threshold(value: float) -> float:
    if 0 < value <= 1:
        return value * 100
    return min(value, 100.0)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).expanduser()
    if not config_path.exists():
        raise ConfigError(f"配置文件不存在：{config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    if not isinstance(raw, dict):
        raise ConfigError("配置文件顶层必须是对象")

    cpa_raw = _read_mapping(raw.get("cpa"), "cpa")
    inspect_raw = _read_mapping(raw.get("inspect"), "inspect")
    actions_raw = _read_mapping(raw.get("actions"), "actions")
    output_raw = _read_mapping(raw.get("output"), "output")

    base_url = _read_str(cpa_raw, "base_url").rstrip("/")
    management_key = _read_str(cpa_raw, "management_key")
    if not base_url:
        raise ConfigError("缺少 `cpa.base_url`")
    if not management_key:
        raise ConfigError("缺少 `cpa.management_key`")

    threshold = _normalize_threshold(_read_float(inspect_raw, "used_percent_threshold", 100.0))

    return AppConfig(
        cpa=CpaConfig(base_url=base_url, management_key=management_key),
        inspect=InspectConfig(
            target_type=_read_str(inspect_raw, "target_type", "codex").lower() or "codex",
            workers=_read_int(inspect_raw, "workers", 4, minimum=1),
            delete_workers=_read_int(inspect_raw, "delete_workers", 4, minimum=1),
            timeout_seconds=_read_float(inspect_raw, "timeout_seconds", 15.0, minimum=1.0),
            retries=_read_int(inspect_raw, "retries", 0, minimum=0),
            used_percent_threshold=threshold,
            sample_size=_read_int(inspect_raw, "sample_size", 0, minimum=0),
            user_agent=_read_str(
                inspect_raw,
                "user_agent",
                "codex_cli_rs/0.76.0 (Debian 13.0.0; x86_64) WindowsTerminal",
            ),
        ),
        actions=ActionConfig(
            delete_401=_read_bool(actions_raw, "delete_401", True),
            disable_quota_exhausted=_read_bool(actions_raw, "disable_quota_exhausted", True),
            disable_five_hour_exhausted=_read_bool(actions_raw, "disable_five_hour_exhausted", False),
            enable_recovered_disabled=_read_bool(actions_raw, "enable_recovered_disabled", True),
            backup_before_delete=_read_bool(actions_raw, "backup_before_delete", True),
        ),
        output=OutputConfig(
            report_dir=_read_str(output_raw, "report_dir", "./reports") or "./reports",
            backup_dir=_read_str(output_raw, "backup_dir", "./backups") or "./backups",
        ),
    )
