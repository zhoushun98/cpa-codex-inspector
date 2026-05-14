from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from rich.console import Console

from .auth import to_auth_account
from .config import ConfigError, load_config
from .cpa_api import CpaApiClient, CpaApiError
from .inspector import filter_actionable_results, run_inspection
from .models import AppConfig
from .reporting import render_results, timestamp_slug, write_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLIProxyAPI Codex 账号池巡检工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="巡检 Codex 账号池")
    inspect.add_argument("--config", default="config.yaml", help="YAML 配置文件路径，默认 ./config.yaml")
    inspect.add_argument("--apply", action="store_true", help="执行建议动作；默认只报告")
    inspect.add_argument("--workers", type=int, help="覆盖巡检并发数")
    inspect.add_argument("--delete-workers", type=int, help="覆盖删除并发数")
    inspect.add_argument("--sample-size", type=int, help="随机抽样数量；0 表示全量")
    inspect.add_argument("--threshold", type=float, help="额度百分比阈值，例如 100 或 0.9")
    inspect.add_argument(
        "--skip-disabled",
        action="store_true",
        default=None,
        help="跳过已禁用账号，不进行探测；不传则沿用配置文件设置",
    )
    inspect.add_argument("--force-delete-without-backup", action="store_true", help="删除前备份失败时仍继续删除")
    inspect.add_argument("--no-table", action="store_true", help="不输出终端表格，只写 JSON 报告")

    list_cmd = subparsers.add_parser("list", help="列出 Codex 账号")
    list_cmd.add_argument("--config", default="config.yaml", help="YAML 配置文件路径，默认 ./config.yaml")
    list_cmd.add_argument(
        "--skip-disabled",
        action="store_true",
        default=None,
        help="跳过已禁用账号，不在列表中显示；不传则沿用配置文件设置",
    )

    return parser


def apply_overrides(config_path: str, args: argparse.Namespace) -> AppConfig:
    config = load_config(config_path)
    if getattr(args, "workers", None) is not None:
        config.inspect.workers = max(1, args.workers)
    if getattr(args, "delete_workers", None) is not None:
        config.inspect.delete_workers = max(1, args.delete_workers)
    if getattr(args, "sample_size", None) is not None:
        config.inspect.sample_size = max(0, args.sample_size)
    if getattr(args, "threshold", None) is not None:
        threshold = float(args.threshold)
        config.inspect.used_percent_threshold = threshold * 100 if 0 < threshold <= 1 else max(0.0, min(100.0, threshold))
    if getattr(args, "skip_disabled", None) is True:
        config.inspect.skip_disabled = True
    return config


async def command_list(args: argparse.Namespace, console: Console) -> int:
    config = load_config(args.config)
    if getattr(args, "skip_disabled", None) is True:
        config.inspect.skip_disabled = True
    async with CpaApiClient(config) as client:
        files = await client.list_auth_files()
    accounts = [to_auth_account(item) for item in files]
    codex_accounts = [item for item in accounts if item.provider == config.inspect.target_type]
    skipped = 0
    if config.inspect.skip_disabled:
        kept = [item for item in codex_accounts if not item.disabled]
        skipped = len(codex_accounts) - len(kept)
        codex_accounts = kept
    console.print(f"Codex 账号：{len(codex_accounts)} / 总认证文件：{len(files)}")
    if skipped:
        console.print(f"已跳过 {skipped} 个已禁用账号（--skip-disabled）")
    for item in codex_accounts:
        state = "disabled" if item.disabled else "enabled"
        console.print(f"- {item.display_account} | {item.file_name} | {item.auth_index or '-'} | {state}")
    return 0


async def command_inspect(args: argparse.Namespace, console: Console) -> int:
    config = apply_overrides(args.config, args)
    slug = timestamp_slug()
    backup_dir = str(Path(config.output.backup_dir).expanduser() / slug)
    run = await run_inspection(
        config,
        apply=args.apply,
        backup_dir=backup_dir,
        force_delete_without_backup=args.force_delete_without_backup,
    )
    report_path = write_report(run, config.output.report_dir, slug=slug)
    if not args.no_table:
        render_results(run, console)
    console.print(f"JSON 报告：[bold]{report_path}[/bold]")

    actionable = filter_actionable_results(run.results, config)
    failed_outcomes = [item for item in run.outcomes if not item.success]
    if failed_outcomes:
        return 3
    if actionable and not args.apply:
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()
    try:
        if args.command == "list":
            return asyncio.run(command_list(args, console))
        if args.command == "inspect":
            return asyncio.run(command_inspect(args, console))
    except ConfigError as error:
        console.print(f"[red]配置错误：{error}[/red]")
        return 1
    except CpaApiError as error:
        console.print(f"[red]CPA API 错误：{error}[/red]")
        return 1
    except KeyboardInterrupt:
        console.print("[yellow]已中断[/yellow]")
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

