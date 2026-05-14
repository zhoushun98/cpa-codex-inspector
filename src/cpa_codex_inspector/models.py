from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Action = Literal["keep", "delete", "disable", "enable"]


@dataclass(slots=True)
class CpaConfig:
    base_url: str
    management_key: str


@dataclass(slots=True)
class InspectConfig:
    target_type: str = "codex"
    workers: int = 4
    delete_workers: int = 4
    timeout_seconds: float = 15.0
    retries: int = 0
    used_percent_threshold: float = 100.0
    sample_size: int = 0
    user_agent: str = "codex_cli_rs/0.76.0 (Debian 13.0.0; x86_64) WindowsTerminal"
    skip_disabled: bool = False


@dataclass(slots=True)
class ActionConfig:
    delete_401: bool = True
    disable_quota_exhausted: bool = True
    disable_five_hour_exhausted: bool = False
    enable_recovered_disabled: bool = True
    backup_before_delete: bool = True


@dataclass(slots=True)
class OutputConfig:
    report_dir: str = "./reports"
    backup_dir: str = "./backups"


@dataclass(slots=True)
class AppConfig:
    cpa: CpaConfig
    inspect: InspectConfig = field(default_factory=InspectConfig)
    actions: ActionConfig = field(default_factory=ActionConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


@dataclass(slots=True)
class AuthAccount:
    key: str
    file_name: str
    display_account: str
    auth_index: str | None
    account_id: str | None
    provider: str
    disabled: bool
    status: str
    state: str
    raw: dict[str, Any]


@dataclass(slots=True)
class InspectionResult:
    account: AuthAccount
    action: Action
    action_reason: str
    status_code: int | None
    used_percent: float | None
    is_quota: bool
    error: str = ""


@dataclass(slots=True)
class ExecutionOutcome:
    action: Literal["delete", "disable", "enable"]
    file_name: str
    display_account: str
    success: bool
    error: str = ""
    backup_path: str = ""


@dataclass(slots=True)
class InspectionRun:
    started_at: str
    finished_at: str
    settings: dict[str, Any]
    total_files: int
    probe_set_count: int
    sampled_count: int
    results: list[InspectionResult]
    outcomes: list[ExecutionOutcome] = field(default_factory=list)
