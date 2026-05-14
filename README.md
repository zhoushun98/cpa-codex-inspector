# cpa-codex-inspector

独立的 CLIProxyAPI Codex 账号池巡检工具。它通过 CPA Management API 列出认证文件，使用 CPA 的 `/api-call` 代理探测 Codex usage 接口，然后给出删除、禁用、启用或保留建议。

默认只报告，不会改账号。必须显式加 `--apply` 才会执行删除、禁用、启用。

## 功能

- 只巡检 `provider/type = codex` 的认证文件。
- 401 失效账号建议删除。
- 402、quota exhausted、limit reached、payment_required 或周额度达到阈值时建议禁用。
- 已禁用账号在短周期和周额度都恢复可用时建议启用。
- 5 小时额度耗尽但周额度仍可用时默认保留；可配置为临时禁用。
- 支持 `skip_disabled` 开关；开启后已禁用账号既不被探测也不会被自动启用。
- 删除前默认下载认证文件备份，备份失败会跳过删除。
- 输出终端表格和 JSON 报告，便于人工查看或 cron 归档。

## 安装

```bash
cd /Users/jason/cpa-codex-inspector
uv sync
```

## 配置

复制示例配置后修改：

```bash
cp config.example.yaml config.yaml
```

最小配置：

```yaml
cpa:
  base_url: "http://127.0.0.1:38317"
  management_key: "${CPA_MANAGEMENT_KEY}"
```

完整配置见 [config.example.yaml](/Users/jason/cpa-codex-inspector/config.example.yaml)。

如果希望 5 小时额度满时也临时禁用账号，开启：

```yaml
actions:
  disable_five_hour_exhausted: true
  enable_recovered_disabled: true
```

开启后，后续巡检发现该账号 5 小时额度和周额度都低于阈值，会重新建议启用。仍然需要加 `--apply` 才会真正修改账号状态。

如果不想让已禁用账号继续被探测（例如手动封存的账号），开启：

```yaml
inspect:
  skip_disabled: true
```

开启后，这些账号不会出现在 `inspect` 与 `list` 输出里，也不会触发自动启用。如需重新纳入巡检，把 `skip_disabled` 改回 `false`，下一次带 `--apply` 的巡检会按现有逻辑重新判定并启用。

## 使用

列出 Codex 账号：

```bash
uv run cpa-codex-inspector list --config config.yaml
```

巡检但不执行动作：

```bash
uv run cpa-codex-inspector inspect --config config.yaml
```

巡检并执行建议动作：

```bash
uv run cpa-codex-inspector inspect --config config.yaml --apply
```

`--config` 默认为当前目录的 `config.yaml`，所以下方第 4 行示例省略了它：

常用覆盖参数：

```bash
uv run cpa-codex-inspector inspect --config config.yaml --workers 8 --delete-workers 4 --threshold 100
uv run cpa-codex-inspector inspect --config config.yaml --sample-size 50
uv run cpa-codex-inspector inspect --config config.yaml --apply --force-delete-without-backup
uv run cpa-codex-inspector inspect --skip-disabled
```

`--force-delete-without-backup` 只影响删除动作：备份失败时仍继续删除。平时不建议开启。

## 输出

- JSON 报告默认写入 `./reports/codex-inspection-YYYYMMDD-HHMMSS.json`。
- 删除前备份默认写入 `./backups/YYYYMMDD-HHMMSS/`。
- `inspect --no-table` 可关闭终端表格，只生成 JSON 报告。

退出码：

- `0`：巡检完成，且没有待执行动作或执行成功。
- `1`：配置或 CPA API 调用失败。
- `2`：dry-run 模式发现可执行动作，但未加 `--apply`。
- `3`：`--apply` 后存在执行失败的动作。
- `130`：手动中断。

## Cron 示例

每 30 分钟 dry-run 巡检一次：

```cron
CPA_MANAGEMENT_KEY=CHANGE_ME
*/30 * * * * cd /Users/jason/cpa-codex-inspector && uv run cpa-codex-inspector inspect --config /path/to/config.yaml --no-table >> /var/log/cpa-codex-inspector.log 2>&1
```

> 由于 cron 已 `cd` 进项目根目录，也可以省略 `--config`，让程序读取当前目录下的 `config.yaml`。

如果确认策略稳定，再把 cron 改成执行模式：

```cron
*/30 * * * * cd /Users/jason/cpa-codex-inspector && uv run cpa-codex-inspector inspect --config /path/to/config.yaml --apply --no-table >> /var/log/cpa-codex-inspector.log 2>&1
```

## 开发验证

```bash
uv run pytest
uv run cpa-codex-inspector --help
uv run cpa-codex-inspector inspect --help
```
