#!/usr/bin/env python3
"""Keep Cursor open and run the collector once per day at a configured time."""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path


def load_run_time(repo_root: Path) -> str:
    env_path = repo_root / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("RUN_AT_LOCAL_TIME="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("RUN_AT_LOCAL_TIME", "08:00")


def seconds_until_next(run_time: str) -> int:
    hour_text, minute_text = run_time.split(":", 1)
    now = dt.datetime.now()
    target = now.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return max(int((target - now).total_seconds()), 1)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    run_time = load_run_time(repo_root)
    print(f"Cursor 常驻定时已启动。每天本机时间 {run_time} 运行一次。按 Ctrl+C 可停止。", flush=True)
    while True:
        wait_seconds = seconds_until_next(run_time)
        next_time = dt.datetime.now() + dt.timedelta(seconds=wait_seconds)
        print(f"下一次运行：{next_time:%Y-%m-%d %H:%M:%S}", flush=True)
        time.sleep(wait_seconds)
        print("开始运行采集脚本...", flush=True)
        subprocess.run([sys.executable, str(repo_root / "vibe_case_collector.py")], cwd=repo_root, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
