import copy
import json
import os
import sys

HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
CONFIG_NAME = "config.json"

DEFAULT_CONFIG = {
    "display": {
        "separator": ": ",
        "keyPrefix": "",
        "keyWidth": 0,
        "indent": 0,
        "keyColor": "#e8414b",
        "titleColor": "#e8414b",
        "textColor": "#e2e2e2",
        "separatorColor": "#969696",
    },
    "modules": [
        "title",
        "separator",
        "os",
        "host",
        "kernel",
        "uptime",
        "packages",
        "shell",
        "display",
        "de",
        "wm",
        "wmtheme",
        "theme",
        "cursor",
        "terminal",
        "cpu",
        "gpu",
        "memory",
        "swap",
        "disk",
        "localip",
        "battery",
        "locale",
        "break",
        "colors",
    ],
}


def _merge(base, extra):
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _candidates(path):
    return [p for p in (path, os.environ.get("VOXELFETCH_CONFIG"), os.path.join(HERE, CONFIG_NAME)) if p]


def load_config(path=None):
    config = copy.deepcopy(DEFAULT_CONFIG)
    for candidate in _candidates(path):
        if not os.path.isfile(candidate):
            if candidate == path:
                print(f"voxelfetch: config not found: {candidate}", file=sys.stderr)
            continue
        try:
            with open(candidate, encoding="utf-8-sig") as fh:
                user = json.load(fh)
            if not isinstance(user, dict):
                raise ValueError("top level must be an object")
            if not isinstance(user.get("modules", []), list):
                raise ValueError("'modules' must be a list")
            return _merge(config, user)
        except (OSError, ValueError) as exc:
            print(f"voxelfetch: bad config {candidate}: {exc}; using defaults", file=sys.stderr)
            break
    return config


if __name__ == "__main__":
    print(json.dumps(DEFAULT_CONFIG, indent=2))
