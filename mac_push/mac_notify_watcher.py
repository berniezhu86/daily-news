#!/usr/bin/env python3
"""Poll latest_push_news.json and show macOS local notifications."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUSH_FILE = ROOT / "latest_push_news.json"
SEEN_FILE = ROOT / "mac_push" / "seen_push_ids.json"
CONFIG_FILE = ROOT / "mac_push" / "push_config.json"
DEFAULT_CONFIG = {
    "poll_seconds": 300,
    "enabled": True,
    "enabled_types": ["high_politics", "breaking", "football", "market"],
    "max_normal_per_day": 5,
    "app_name": "臻宝每日快讯",
}


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def notify(title: str, message: str, subtitle: str = "") -> None:
    # osascript notifications work without extra packages and can later be replaced
    # by Electron/Tauri native notification APIs.
    def esc(s: str) -> str:
        return s.replace('\\', '\\\\').replace('"', '\\"')
    script = f'display notification "{esc(message)}" with title "{esc(title)}"'
    if subtitle:
        script += f' subtitle "{esc(subtitle)}"'
    subprocess.run(["osascript", "-e", script], check=False)


def today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def process_once(config: dict) -> int:
    if not config.get("enabled", True) or not PUSH_FILE.exists():
        return 0
    payload = load_json(PUSH_FILE, {})
    seen = load_json(SEEN_FILE, {"ids": [], "daily": {}})
    seen_ids = set(seen.get("ids", []))
    daily = seen.setdefault("daily", {})
    day = today_key()
    daily.setdefault(day, {"normal": 0})
    sent = 0
    enabled_types = set(config.get("enabled_types") or [])
    max_normal = int(config.get("max_normal_per_day") or 5)
    app_name = config.get("app_name") or "臻宝每日快讯"

    for item in payload.get("items", []):
        item_id = item.get("id")
        if not item_id or item_id in seen_ids:
            continue
        kind = item.get("type")
        if enabled_types and kind not in enabled_types:
            continue
        priority = item.get("priority", "normal")
        if priority != "high" and daily[day].get("normal", 0) >= max_normal:
            continue
        title = item.get("title", "新闻更新")
        message = item.get("summary") or item.get("source") or "有新的重要新闻"
        subtitle = f"{app_name} · {item.get('section', '')}"
        notify(title, message, subtitle)
        seen_ids.add(item_id)
        sent += 1
        if priority != "high":
            daily[day]["normal"] = daily[day].get("normal", 0) + 1

    seen["ids"] = list(seen_ids)[-500:]
    # Keep a short daily history.
    seen["daily"] = dict(sorted(daily.items())[-14:])
    save_json(SEEN_FILE, seen)
    return sent


def main() -> None:
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    if not CONFIG_FILE.exists():
        save_json(CONFIG_FILE, DEFAULT_CONFIG)
    config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
    once = "--once" in sys.argv
    dry = "--dry-run" in sys.argv
    if dry:
        payload = load_json(PUSH_FILE, {})
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if once:
        print(process_once(config))
        return
    while True:
        config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
        process_once(config)
        time.sleep(int(config.get("poll_seconds") or 300))


if __name__ == "__main__":
    main()
