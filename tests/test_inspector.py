from __future__ import annotations

from pathlib import Path

import pytest

from cpa_codex_inspector.inspector import (
    backup_file_name,
    execute_actions,
    filter_actionable_results,
    inspect_accounts,
)
from cpa_codex_inspector.models import AppConfig, AuthAccount, CpaConfig, InspectionResult


def _account(file_name: str = "codex.json") -> AuthAccount:
    return AuthAccount(
        key=f"{file_name}::1",
        file_name=file_name,
        display_account="user@example.com",
        auth_index="1",
        account_id=None,
        provider="codex",
        disabled=False,
        status="enabled",
        state="",
        raw={},
    )


def _result(action: str, file_name: str = "codex.json") -> InspectionResult:
    return InspectionResult(
        account=_account(file_name),
        action=action,  # type: ignore[arg-type]
        action_reason="测试",
        status_code=401 if action == "delete" else 200,
        used_percent=None,
        is_quota=False,
    )


def _config() -> AppConfig:
    return AppConfig(cpa=CpaConfig(base_url="http://cpa.local", management_key="secret"))


class FakeClient:
    def __init__(self, *, backup_error: Exception | None = None) -> None:
        self.backup_error = backup_error
        self.deleted: list[list[str]] = []
        self.status_updates: list[tuple[str, bool]] = []

    async def download_auth_file(self, name: str) -> bytes:
        if self.backup_error:
            raise self.backup_error
        return f"backup:{name}".encode()

    async def delete_auth_files(self, names: list[str]) -> dict:
        self.deleted.append(names)
        return {}

    async def set_auth_file_disabled(self, name: str, disabled: bool) -> dict:
        self.status_updates.append((name, disabled))
        return {}


def test_filter_actionable_results_dedupes_by_file_name() -> None:
    results = [_result("delete", "same.json"), _result("disable", "same.json"), _result("keep", "keep.json")]

    actionable = filter_actionable_results(results, _config())

    assert [item.action for item in actionable] == ["delete"]


def test_backup_file_name_removes_path_separators() -> None:
    assert backup_file_name("../codex.json") == "..__codex.json"
    assert backup_file_name(r"folder\codex.json") == "folder__codex.json"


@pytest.mark.asyncio
async def test_execute_actions_skips_delete_when_backup_fails(tmp_path: Path) -> None:
    client = FakeClient(backup_error=RuntimeError("download failed"))

    outcomes = await execute_actions(client, _config(), [_result("delete")], backup_dir=str(tmp_path))

    assert outcomes[0].success is False
    assert "备份失败" in outcomes[0].error
    assert client.deleted == []


@pytest.mark.asyncio
async def test_execute_actions_backs_up_then_deletes(tmp_path: Path) -> None:
    client = FakeClient()

    outcomes = await execute_actions(client, _config(), [_result("delete", "../codex.json")], backup_dir=str(tmp_path))

    assert outcomes[0].success is True
    assert client.deleted == [["../codex.json"]]
    assert (tmp_path / "..__codex.json").read_bytes() == b"backup:../codex.json"


class FakeListClient:
    def __init__(self, files: list[dict]) -> None:
        self.files = files
        self.api_calls: list[dict] = []

    async def list_auth_files(self) -> list[dict]:
        return self.files

    async def api_call(self, **kwargs: object) -> dict:
        self.api_calls.append(kwargs)
        return {"status_code": 200, "body": ""}


def _file(name: str, *, disabled: bool) -> dict:
    return {
        "name": name,
        "auth_index": name.replace(".json", ""),
        "provider": "codex",
        "disabled": disabled,
        "account": f"{name}@example.com",
    }


@pytest.mark.asyncio
async def test_inspect_accounts_skips_disabled_when_enabled() -> None:
    files = [_file("a.json", disabled=False), _file("b.json", disabled=True)]
    client = FakeListClient(files)
    config = _config()
    config.inspect.skip_disabled = True

    fetched_files, sampled, results = await inspect_accounts(client, config)  # type: ignore[arg-type]

    assert {item.file_name for item in sampled} == {"a.json"}
    assert {item.account.file_name for item in results} == {"a.json"}
    assert len(fetched_files) == 2


@pytest.mark.asyncio
async def test_inspect_accounts_includes_disabled_by_default() -> None:
    files = [_file("a.json", disabled=False), _file("b.json", disabled=True)]
    client = FakeListClient(files)
    config = _config()

    _, sampled, results = await inspect_accounts(client, config)  # type: ignore[arg-type]

    assert {item.file_name for item in sampled} == {"a.json", "b.json"}
    assert {item.account.file_name for item in results} == {"a.json", "b.json"}
