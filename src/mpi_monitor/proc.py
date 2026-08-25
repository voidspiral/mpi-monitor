"""Parse Linux /proc process accounting files."""

from __future__ import annotations

import os
from typing import Any

try:
    DEFAULT_CLK_TCK = os.sysconf("SC_CLK_TCK")
except (ValueError, OSError):
    DEFAULT_CLK_TCK = 100


def parse_stat(text: str) -> dict[str, Any]:
    lparen = text.find("(")
    rparen = text.rfind(")")
    if lparen < 0 or rparen < 0 or rparen <= lparen:
        raise ValueError("invalid /proc/pid/stat")
    pid = int(text[:lparen].strip())
    comm = text[lparen + 1 : rparen]
    rest = text[rparen + 1 :].split()
    utime = int(rest[11])
    stime = int(rest[12])
    return {
        "pid": pid,
        "comm": comm,
        "utime": utime,
        "stime": stime,
        "cpu_ticks": utime + stime,
    }


def parse_status_vmrss_kb(text: str) -> int | None:
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            return int(parts[1])
    return None


def parse_io(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            out[key] = int(value)
    return out


def cpu_pct(
    prev_ticks: int,
    curr_ticks: int,
    elapsed_sec: float,
    clk_tck: int = DEFAULT_CLK_TCK,
) -> float:
    if elapsed_sec <= 0 or clk_tck <= 0:
        return 0.0
    return ((curr_ticks - prev_ticks) / clk_tck) / elapsed_sec * 100.0


def rss_mb(kb: int) -> float:
    return kb / 1024.0


def io_bps(prev: int, curr: int, elapsed_sec: float) -> float:
    if elapsed_sec <= 0:
        return 0.0
    return (curr - prev) / elapsed_sec
