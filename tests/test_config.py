import dataclasses
import json

from mimo_usage_monitor.config import AppConfig, data_dir, load_config, save_config


def test_load_config_missing_returns_defaults(tmp_path):
    assert load_config(tmp_path) == AppConfig()


def test_load_config_corrupt_json_returns_defaults(tmp_path):
    (tmp_path / "config.json").write_bytes(b"{bad json")
    assert load_config(tmp_path) == AppConfig()


def test_save_load_roundtrip(tmp_path):
    cfg = dataclasses.replace(
        AppConfig(),
        refresh_interval_s=300,
        show_taskbar=True,
        floating_rect=(10, 20, 380, 76),
    )
    save_config(tmp_path, cfg)
    assert load_config(tmp_path) == cfg


def test_refresh_interval_clamped(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"refresh_interval_s": 25}), encoding="utf-8"
    )
    assert load_config(tmp_path).refresh_interval_s == 30
    (tmp_path / "config.json").write_text(
        json.dumps({"refresh_interval_s": 9999}), encoding="utf-8"
    )
    assert load_config(tmp_path).refresh_interval_s == 600


def test_data_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MIMO_MONITOR_HOME", str(tmp_path))
    assert data_dir() == tmp_path


def test_load_migrates_old_default_rect(tmp_path):
    (tmp_path / "config.json").write_text(
        json.dumps({"floating_rect": [0, 0, 380, 76]}), encoding="utf-8"
    )
    assert load_config(tmp_path).floating_rect == (0, 0, 360, 36)
