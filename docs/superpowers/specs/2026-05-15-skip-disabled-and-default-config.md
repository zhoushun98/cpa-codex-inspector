# Spec：跳过已禁用账号开关 + config 默认路径

- 日期：2026-05-15
- 影响版本：cpa-codex-inspector 0.1.x

## 背景

当前 `inspect` / `list` 子命令均要求显式 `--config <path>`，且不论账号是否已禁用都会被纳入 Codex 探测集合。在 cron 长期运行场景里：

- 多数用户的配置文件都放在项目根目录的 `config.yaml`，每次都写 `--config /path/to/config.yaml` 是冗余。
- 一旦某账号已经被禁用，业务方往往希望它保持禁用状态（例如手动封存），不希望自动巡检再去消耗其 5 小时额度或周额度去判定是否恢复，也不希望出现"自动重新启用"的副作用。

本次改动给上述两个痛点各加一个开关。

## 目标

1. `inspect` 与 `list` 的 `--config` 参数默认值改为 `config.yaml`（仍允许显式覆盖）。
2. 引入 `skip_disabled` 开关，开启后从 `inspect` 与 `list` 的目标集合中排除 `disabled=true` 的认证文件。

## 非目标

- 不引入"仅扫描已禁用账号以判断是否恢复"的独立模式。开启 `skip_disabled` 后，已禁用账号既不被探测也不被自动启用——这是逻辑必然，不在本 spec 范围内。
- 不调整现有决策矩阵（`quota.py`）。
- 不调整删除/禁用/启用动作的执行流程。

## 设计

### 配置层（`src/cpa_codex_inspector/models.py` + `config.py`）

`InspectConfig` 增加字段：

```python
skip_disabled: bool = False
```

`load_config` 读取 yaml：

```python
skip_disabled=_read_bool(inspect_raw, "skip_disabled", False),
```

默认 `false`，保持向后兼容。

### CLI 层（`src/cpa_codex_inspector/cli.py`）

- `inspect` 与 `list` 子命令的 `--config`：
  - 由 `required=True` 改为 `default="config.yaml"`
  - help 文案更新为 "YAML 配置文件路径，默认 ./config.yaml"
- `inspect` 与 `list` 子命令新增 `--skip-disabled` 参数：
  - `action="store_true"`、`default=None`
  - `None` 表示沿用 yaml 中的 `inspect.skip_disabled`
  - 命令行显式传入 `True` 时覆盖为 `True`
- `apply_overrides` 增加分支：

  ```python
  if getattr(args, "skip_disabled", None) is True:
      config.inspect.skip_disabled = True
  ```

  `list` 命令目前不走 `apply_overrides`，需要新增一段轻量覆盖逻辑（或将 `apply_overrides` 中通用字段抽出复用）。优先选择"在 `command_list` 内联同样的 if 分支"，避免提前抽象。

- `command_list` 输出循环前按 `config.inspect.skip_disabled` 过滤 `codex_accounts`。摘要打印保持显示"Codex 账号：M / 总认证文件：N"，其中 M 为过滤后的数量；额外增加一行说明跳过了多少个 disabled 账号，便于人工核对。

### 探测层（`src/cpa_codex_inspector/inspector.py`）

`inspect_accounts` 中构造 `probe_set` 时：

```python
probe_set = [item for item in accounts if item.provider == config.inspect.target_type]
if config.inspect.skip_disabled:
    probe_set = [item for item in probe_set if not item.disabled]
```

`InspectionRun.probe_set_count` 保留为"全部 Codex 账号数（未按 disabled 过滤）"，便于在报告 JSON 中直接看出"总共 N 个 Codex 账号，本次跳过禁用后探测 K 个"。`sampled_count` 自然等于实际进入并发探测的数量。

`run_inspection` 已读 `to_auth_account(file)` 计算 `probe_set_count`，保持现状不动。

### 报告层

`InspectionRun.settings` 字典在 `run_inspection` 中追加 `skip_disabled: bool`，让 JSON 报告自包含巡检策略。

### 文档 & 配置示例

- `config.example.yaml`：在 `inspect:` 块下加 `skip_disabled: false` 并附注释。
- `README.md`：
  - "配置"小节补充 `skip_disabled` 字段说明，明确"开启后已禁用账号不会被探测，也不会被自动启用"。
  - "使用"小节给一个 `--skip-disabled` 示例命令。
  - "Cron 示例"小节把 `--config /path/to/config.yaml` 注释改为可选，提示当 cwd 内有 `config.yaml` 时可省略。

## 测试

`tests/test_config.py`：

- 新增 case：yaml 含 `inspect.skip_disabled: true` 时 `config.inspect.skip_disabled is True`。
- 已有 case 不变（默认值 `False`）。

`tests/test_inspector.py`：

- 新增 case：构造一组 Codex 账号（部分 `disabled=True`），开启 `config.inspect.skip_disabled` 后调用 `inspect_accounts`（mock CPA 客户端），断言：
  - `results` 中不含任何 `account.disabled is True` 的条目。
  - `probe_set_count` 等于全部 Codex 账号总数（含 disabled）。
  - `sampled_count` 等于过滤后的数量。

`tests/test_cli.py`（如不存在则新建）：

- 新增 case：`--skip-disabled` 命令行参数能把 `config.inspect.skip_disabled` 从 `False` 改为 `True`。

## 取舍说明

- **`--skip-disabled` 只能开不能关**：使用 `store_true` 形式，无法在命令行上把 yaml 中已设为 `true` 的开关临时关掉。理由：yaml 是显式策略来源，CLI 仅作为 cron 之外的临时快捷方式；若未来确有需求，可再引入 `--no-skip-disabled` 配对参数。
- **`probe_set_count` 不随 `skip_disabled` 变化**：保持"目标集合 = 全部 Codex 账号"这一语义稳定，方便观察"被跳过的禁用账号占比"。`sampled_count` 才是实际探测数。
- **`list` 命令也生效**：与 `inspect` 共享同一个"待巡检集合"语义，避免出现 list 显示 50 个、inspect 只跑 30 个的疑惑。

## 退出码与外部行为

无新增退出码。开启 `skip_disabled` 不会改变现有 0/1/2/3/130 的语义。

## 兼容性

- yaml 不写 `skip_disabled` 时与旧版行为一致。
- CLI 不传 `--skip-disabled` 时与旧版行为一致。
- 旧脚本继续显式传 `--config /path/to/config.yaml` 时不受影响。
