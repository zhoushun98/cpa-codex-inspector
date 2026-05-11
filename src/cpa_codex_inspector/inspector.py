from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from typing import Any, Literal, cast

from .auth import to_auth_account
from .cpa_api import CpaApiClient
from .models import AppConfig, AuthAccount, ExecutionOutcome, InspectionResult, InspectionRun
from .quota import CODEX_USAGE_URL, parse_usage_payload, resolve_probe_action

StatusAction = Literal["disable", "enable"]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def pick_sample(items: list[AuthAccount], sample_size: int) -> list[AuthAccount]:
    if sample_size <= 0 or sample_size >= len(items):
        return list(items)
    shuffled = list(items)
    random.shuffle(shuffled)
    return shuffled[:sample_size]


def backup_file_name(file_name: str) -> str:
    safe_name = file_name.replace("/", "__").replace("\\", "__").strip()
    return safe_name or "auth-file"


async def _with_retry(retries: int, task: Any) -> Any:
    last_error: Exception | None = None
    for _ in range(retries + 1):
        try:
            return await task()
        except Exception as error:  # noqa: BLE001 - 这里需要保留最后一次失败原因
            last_error = error
    raise last_error or RuntimeError("未知重试错误")


async def inspect_account(client: CpaApiClient, account: AuthAccount, config: AppConfig) -> InspectionResult:
    if not account.auth_index:
        return InspectionResult(
            account=account,
            action="keep",
            action_reason="缺少 auth_index，保留账号",
            status_code=None,
            used_percent=None,
            is_quota=False,
            error="缺少 auth_index",
        )

    headers = {
        "Authorization": "Bearer $TOKEN$",
        "Content-Type": "application/json",
        "User-Agent": config.inspect.user_agent,
    }
    if account.account_id:
        headers["Chatgpt-Account-Id"] = account.account_id

    async def call() -> dict[str, Any]:
        return await client.api_call(
            auth_index=account.auth_index or "",
            method="GET",
            url=CODEX_USAGE_URL,
            headers=headers,
        )

    try:
        result = await _with_retry(config.inspect.retries, call)
    except Exception as error:  # noqa: BLE001 - 单账号失败不应中断全局巡检
        return InspectionResult(
            account=account,
            action="keep",
            action_reason="探测异常，保留账号",
            status_code=None,
            used_percent=None,
            is_quota=False,
            error=str(error),
        )

    raw_status = result.get("status_code") or result.get("statusCode")
    try:
        status_code = int(raw_status)
    except (TypeError, ValueError):
        return InspectionResult(
            account=account,
            action="keep",
            action_reason="探测响应缺少 status_code，保留账号",
            status_code=None,
            used_percent=None,
            is_quota=False,
            error="响应缺少 status_code",
        )

    body_text = str(result.get("body") or "")
    payload = parse_usage_payload(result.get("body"))
    return resolve_probe_action(
        account,
        status_code,
        body_text,
        payload,
        config.inspect.used_percent_threshold,
        disable_five_hour_exhausted=config.actions.disable_five_hour_exhausted,
    )


async def inspect_accounts(client: CpaApiClient, config: AppConfig) -> tuple[list[dict[str, Any]], list[AuthAccount], list[InspectionResult]]:
    files = await client.list_auth_files()
    accounts = [to_auth_account(item) for item in files]
    probe_set = [item for item in accounts if item.provider == config.inspect.target_type]
    sampled = pick_sample(probe_set, config.inspect.sample_size)

    semaphore = asyncio.Semaphore(config.inspect.workers)

    async def run_one(account: AuthAccount) -> InspectionResult:
        async with semaphore:
            return await inspect_account(client, account, config)

    results = await asyncio.gather(*(run_one(account) for account in sampled))
    results.sort(key=lambda item: (item.account.file_name, item.account.display_account, item.account.key))
    return files, sampled, list(results)


def filter_actionable_results(results: list[InspectionResult], config: AppConfig) -> list[InspectionResult]:
    actionable: list[InspectionResult] = []
    for result in results:
        if result.action == "delete" and config.actions.delete_401:
            actionable.append(result)
        elif result.action == "disable" and config.actions.disable_quota_exhausted:
            actionable.append(result)
        elif result.action == "enable" and config.actions.enable_recovered_disabled:
            actionable.append(result)
    deduped: dict[str, InspectionResult] = {}
    for item in actionable:
        deduped.setdefault(item.account.file_name, item)
    return sorted(deduped.values(), key=lambda item: item.account.file_name)


async def execute_actions(
    client: CpaApiClient,
    config: AppConfig,
    results: list[InspectionResult],
    *,
    backup_dir: str,
    force_delete_without_backup: bool = False,
) -> list[ExecutionOutcome]:
    from pathlib import Path

    actionable = filter_actionable_results(results, config)
    outcomes: list[ExecutionOutcome] = []

    delete_items = [item for item in actionable if item.action == "delete"]
    status_items = [item for item in actionable if item.action in {"disable", "enable"}]
    backup_root = Path(backup_dir)

    delete_semaphore = asyncio.Semaphore(config.inspect.delete_workers)

    async def delete_one(item: InspectionResult) -> ExecutionOutcome:
        async with delete_semaphore:
            backup_path = ""
            if config.actions.backup_before_delete:
                target = backup_root / backup_file_name(item.account.file_name)
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    data = await client.download_auth_file(item.account.file_name)
                    target.write_bytes(data)
                    backup_path = str(target)
                except Exception as error:  # noqa: BLE001
                    if not force_delete_without_backup:
                        return ExecutionOutcome(
                            action="delete",
                            file_name=item.account.file_name,
                            display_account=item.account.display_account,
                            success=False,
                            error=f"删除前备份失败：{error}",
                        )
            try:
                await client.delete_auth_files([item.account.file_name])
            except Exception as error:  # noqa: BLE001
                return ExecutionOutcome(
                    action="delete",
                    file_name=item.account.file_name,
                    display_account=item.account.display_account,
                    success=False,
                    error=str(error),
                    backup_path=backup_path,
                )
            return ExecutionOutcome(
                action="delete",
                file_name=item.account.file_name,
                display_account=item.account.display_account,
                success=True,
                backup_path=backup_path,
            )

    async def status_one(item: InspectionResult) -> ExecutionOutcome:
        if item.action not in {"disable", "enable"}:
            raise ValueError(f"不支持的状态动作：{item.action}")
        action = cast(StatusAction, item.action)
        disabled = item.action == "disable"
        try:
            await client.set_auth_file_disabled(item.account.file_name, disabled)
        except Exception as error:  # noqa: BLE001
            return ExecutionOutcome(
                action=action,
                file_name=item.account.file_name,
                display_account=item.account.display_account,
                success=False,
                error=str(error),
            )
        return ExecutionOutcome(
            action=action,
            file_name=item.account.file_name,
            display_account=item.account.display_account,
            success=True,
        )

    outcomes.extend(await asyncio.gather(*(delete_one(item) for item in delete_items)))
    status_semaphore = asyncio.Semaphore(config.inspect.workers)

    async def status_one_limited(item: InspectionResult) -> ExecutionOutcome:
        async with status_semaphore:
            return await status_one(item)

    outcomes.extend(await asyncio.gather(*(status_one_limited(item) for item in status_items)))
    return outcomes


async def run_inspection(
    config: AppConfig,
    *,
    apply: bool = False,
    backup_dir: str = "",
    force_delete_without_backup: bool = False,
) -> InspectionRun:
    started_at = now_iso()
    async with CpaApiClient(config) as client:
        files, sampled_accounts, results = await inspect_accounts(client, config)
        outcomes: list[ExecutionOutcome] = []
        if apply:
            outcomes = await execute_actions(
                client,
                config,
                results,
                backup_dir=backup_dir,
                force_delete_without_backup=force_delete_without_backup,
            )
    return InspectionRun(
        started_at=started_at,
        finished_at=now_iso(),
        settings={
            "target_type": config.inspect.target_type,
            "workers": config.inspect.workers,
            "delete_workers": config.inspect.delete_workers,
            "timeout_seconds": config.inspect.timeout_seconds,
            "retries": config.inspect.retries,
            "used_percent_threshold": config.inspect.used_percent_threshold,
            "sample_size": config.inspect.sample_size,
            "apply": apply,
            "actions": {
                "delete_401": config.actions.delete_401,
                "disable_quota_exhausted": config.actions.disable_quota_exhausted,
                "disable_five_hour_exhausted": config.actions.disable_five_hour_exhausted,
                "enable_recovered_disabled": config.actions.enable_recovered_disabled,
                "backup_before_delete": config.actions.backup_before_delete,
            },
        },
        total_files=len(files),
        probe_set_count=len([item for item in (to_auth_account(file) for file in files) if item.provider == config.inspect.target_type]),
        sampled_count=len(sampled_accounts),
        results=results,
        outcomes=outcomes,
    )
