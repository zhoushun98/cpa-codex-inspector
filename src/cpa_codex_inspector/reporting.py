from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.text import Text
from rich.table import Table

from .models import ExecutionOutcome, InspectionResult, InspectionRun


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def action_style(action: str) -> str:
    return {
        "delete": "bold red",
        "disable": "yellow",
        "enable": "green",
        "keep": "dim",
    }.get(action, "")


def format_percent(value: float | None) -> str:
    return "--" if value is None else f"{value:.1f}%"


def summarize_results(results: list[InspectionResult]) -> dict[str, int]:
    return {
        "delete": sum(1 for item in results if item.action == "delete"),
        "disable": sum(1 for item in results if item.action == "disable"),
        "enable": sum(1 for item in results if item.action == "enable"),
        "keep": sum(1 for item in results if item.action == "keep"),
    }


def render_results(run: InspectionRun, console: Console | None = None) -> None:
    console = console or Console()
    summary = summarize_results(run.results)
    console.print(
        f"[bold]Codex 巡检完成[/bold]：总文件 {run.total_files}，目标 {run.probe_set_count}，本次探测 {run.sampled_count}，"
        f"删除 {summary['delete']}，禁用 {summary['disable']}，启用 {summary['enable']}，保留 {summary['keep']}"
    )

    table = Table(show_header=True, header_style="bold magenta", row_styles=["none", "dim"])
    table.add_column("动作", style="bold", no_wrap=True)
    table.add_column("账号")
    table.add_column("文件")
    table.add_column("状态码", justify="right", no_wrap=True)
    table.add_column("已用", justify="right", no_wrap=True)
    table.add_column("当前", no_wrap=True)
    table.add_column("原因")
    table.add_column("错误")

    for item in run.results:
        action_text = Text(item.action, style=action_style(item.action))
        table.add_row(
            action_text,
            item.account.display_account,
            item.account.file_name,
            "--" if item.status_code is None else str(item.status_code),
            format_percent(item.used_percent),
            "disabled" if item.account.disabled else "enabled",
            item.action_reason,
            item.error,
        )
    console.print(table)

    if run.outcomes:
        outcome_table = Table(title="执行结果", show_header=True, header_style="bold cyan")
        outcome_table.add_column("动作", no_wrap=True)
        outcome_table.add_column("账号")
        outcome_table.add_column("文件")
        outcome_table.add_column("结果", no_wrap=True)
        outcome_table.add_column("备份")
        outcome_table.add_column("错误")
        for item in run.outcomes:
            outcome_table.add_row(
                item.action,
                item.display_account,
                item.file_name,
                "[green]成功[/green]" if item.success else "[red]失败[/red]",
                item.backup_path,
                item.error,
            )
        console.print(outcome_table)


def _result_to_dict(item: InspectionResult) -> dict[str, Any]:
    raw = asdict(item)
    return raw


def _outcome_to_dict(item: ExecutionOutcome) -> dict[str, Any]:
    return asdict(item)


def run_to_dict(run: InspectionRun) -> dict[str, Any]:
    summary = summarize_results(run.results)
    return {
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "settings": run.settings,
        "summary": {
            "total_files": run.total_files,
            "probe_set_count": run.probe_set_count,
            "sampled_count": run.sampled_count,
            **summary,
        },
        "results": [_result_to_dict(item) for item in run.results],
        "outcomes": [_outcome_to_dict(item) for item in run.outcomes],
    }


def write_report(run: InspectionRun, report_dir: str, *, slug: str | None = None) -> Path:
    path = Path(report_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    report_path = path / f"codex-inspection-{slug or timestamp_slug()}.json"
    report_path.write_text(json.dumps(run_to_dict(run), ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path
