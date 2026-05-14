from __future__ import annotations

from pathlib import Path

from cpa_codex_inspector.cli import apply_overrides, build_parser


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
cpa:
  base_url: "http://cpa.local"
  management_key: "secret"
""",
        encoding="utf-8",
    )
    return path


def test_inspect_config_defaults_to_config_yaml() -> None:
    parser = build_parser()
    args = parser.parse_args(["inspect"])
    assert args.config == "config.yaml"
    assert args.skip_disabled is None


def test_list_config_defaults_to_config_yaml() -> None:
    parser = build_parser()
    args = parser.parse_args(["list"])
    assert args.config == "config.yaml"
    assert args.skip_disabled is None


def test_apply_overrides_sets_skip_disabled_when_flag_passed(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    parser = build_parser()
    args = parser.parse_args(["inspect", "--config", str(config_path), "--skip-disabled"])

    config = apply_overrides(str(config_path), args)

    assert config.inspect.skip_disabled is True


def test_apply_overrides_keeps_yaml_skip_disabled_when_flag_absent(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
cpa:
  base_url: "http://cpa.local"
  management_key: "secret"
inspect:
  skip_disabled: true
""",
        encoding="utf-8",
    )
    parser = build_parser()
    args = parser.parse_args(["inspect", "--config", str(path)])

    config = apply_overrides(str(path), args)

    assert config.inspect.skip_disabled is True
