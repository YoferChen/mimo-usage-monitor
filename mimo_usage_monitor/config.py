import json
import os
from dataclasses import dataclass, fields
from pathlib import Path

CONFIG_FILENAME = "config.json"


@dataclass
class AppConfig:
    refresh_interval_s: int = 60
    threshold_pct: float = 10.0
    notify_enabled: bool = True
    show_tray: bool = True
    show_floating: bool = True
    show_taskbar: bool = False
    floating_rect: tuple[int, int, int, int] = (0, 0, 380, 76)
    floating_opacity: float = 0.9
    floating_locked: bool = False
    autostart: bool = False


def data_dir() -> Path:
    env = os.environ.get("MIMO_MONITOR_HOME")
    if env:
        return Path(env)
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "mimo-usage-monitor"
    return Path.home() / ".config" / "mimo-usage-monitor"


def load_config(data_dir: Path) -> AppConfig:
    path = data_dir / CONFIG_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("config root must be an object")
    except (OSError, ValueError):
        return AppConfig()

    defaults = AppConfig()
    kwargs = {}
    for f in fields(AppConfig):
        if f.name not in raw:
            continue
        value = raw[f.name]
        if f.name == "floating_rect":
            if isinstance(value, (list, tuple)) and len(value) == 4:
                try:
                    kwargs[f.name] = tuple(int(x) for x in value)
                except (TypeError, ValueError):
                    pass
            continue
        target = type(getattr(defaults, f.name))
        try:
            if target is bool:
                if not isinstance(value, bool):
                    raise TypeError("not a bool")
            kwargs[f.name] = target(value)
        except (TypeError, ValueError):
            pass

    cfg = AppConfig(**kwargs)
    cfg.refresh_interval_s = max(30, min(600, int(cfg.refresh_interval_s)))
    return cfg


def save_config(data_dir: Path, cfg: AppConfig) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / CONFIG_FILENAME
    tmp = data_dir / (CONFIG_FILENAME + ".tmp")
    payload = json.dumps(
        {
            **{f.name: getattr(cfg, f.name) for f in fields(AppConfig)},
            "floating_rect": list(cfg.floating_rect),
        },
        ensure_ascii=False,
        indent=2,
    )
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
