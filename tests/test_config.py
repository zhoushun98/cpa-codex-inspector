from __future__ import annotations

from pathlib import Path

import pytest

from cpa_codex_inspector.config import ConfigError, load_config


def test_load_config_normalizes_threshold_and_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CPA_MANAGEMENT_KEY", "env-secret")
    path = tmp_path / "config.yaml"
    path.write_text(
        """
cpa:
  base_url: "http://cpa.local/"
  management_key: "${CPA_MANAGEMENT_KEY}"
inspect:
  used_percent_threshold: 0.9
  workers: 0
actions:
  disable_five_hour_exhausted: true
output:
  report_dir: "./out"
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.cpa.base_url == "http://cpa.local"
    assert config.cpa.management_key == "env-secret"
    assert config.inspect.used_percent_threshold == 90
    assert config.inspect.workers == 1
    assert config.actions.disable_five_hour_exhausted is True
    assert config.output.report_dir == "./out"
    assert config.output.backup_dir == "./backups"


def test_load_config_requires_cpa_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("cpa: {}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="base_url"):
        load_config(path)


def test_load_config_reads_skip_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CPA_MANAGEMENT_KEY", "env-secret")
    path = tmp_path / "config.yaml"
    path.write_text(
        """
cpa:
  base_url: "http://cpa.local"
  management_key: "${CPA_MANAGEMENT_KEY}"
inspect:
  skip_disabled: true
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.inspect.skip_disabled is True


def test_load_config_defaults_skip_disabled_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CPA_MANAGEMENT_KEY", "env-secret")
    path = tmp_path / "config.yaml"
    path.write_text(
        """
cpa:
  base_url: "http://cpa.local"
  management_key: "${CPA_MANAGEMENT_KEY}"
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.inspect.skip_disabled is False
