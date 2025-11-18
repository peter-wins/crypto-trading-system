#!/usr/bin/env python3
"""
Utility script to append entries to UPDATE_LOG.md.

Usage:
    python scripts/add_update_log.py "描述本次更新"

Optional flags:
    --category BUGFIX/FEATURE/etc (default: FEATURE)
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "UPDATE_LOG.md"
HEADER = "# 更新日志\n\n"


def ensure_log_file() -> None:
    if not LOG_PATH.exists():
        LOG_PATH.write_text(HEADER, encoding="utf-8")
        return
    text = LOG_PATH.read_text(encoding="utf-8")
    if not text.startswith("#"):
        LOG_PATH.write_text(HEADER + text, encoding="utf-8")


def append_entry(message: str, category: str) -> None:
    ensure_log_file()
    now = datetime.now(timezone.utc).astimezone()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    existing_lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    last_header = None
    for line in existing_lines:
        if line.startswith("## "):
            last_header = line[3:]

    lines_to_append: list[str] = []
    if last_header != date_str:
        if existing_lines and existing_lines[-1] != "":
            lines_to_append.append("")
        lines_to_append.append(f"## {date_str}")
    entry = f"- [{time_str}] [{category.upper()}] {message}"
    lines_to_append.append(entry)
    lines_to_append.append("")

    with LOG_PATH.open("a", encoding="utf-8") as fp:
        fp.write("\n".join(lines_to_append))


def main() -> None:
    parser = argparse.ArgumentParser(description="Append an update entry to UPDATE_LOG.md")
    parser.add_argument("message", help="更新内容描述")
    parser.add_argument(
        "--category",
        default="FEATURE",
        help="更新类别 (默认: FEATURE)",
    )
    args = parser.parse_args()
    append_entry(args.message.strip(), args.category.strip())


if __name__ == "__main__":
    main()
