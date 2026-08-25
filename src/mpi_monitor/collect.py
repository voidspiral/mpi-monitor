"""Collect process samples to JSONL series files."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mpi_monitor.discover import ProcInfo, discover
from mpi_monitor.proc import (
    DEFAULT_CLK_TCK,
    cpu_pct,
    io_bps,
    parse_io,
    parse_stat,
    parse_status_vmrss_kb,
    rss_mb,
)

SAMPLE_KEYS = (
    "ts",
    "host",
    "pid",
    "cpu_pct",
    "rss_mb",
    "io_read_bps",
    "io_write_bps",
)


def series_filename(host: str, pid: int) -> str:
    return f"{host}_pid{pid}.jsonl"


def series_path(output_dir: Path, host: str, pid: int) -> Path:
    return output_dir / "series" / series_filename(host, pid)


def append_sample(path: Path, sample: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(sample, separators=(",", ":")) + "\n")


@dataclass
class _Prev:
    ts: float
    cpu_ticks: int
    read_bytes: int
    write_bytes: int


def sample_pid(
    proc_dir: Path,
    *,
    host: str,
    pid: int,
    ts: float,
    prev: _Prev | None,
    rank: int | None = None,
    clk_tck: int = DEFAULT_CLK_TCK,
) -> dict[str, Any] | None:
    try:
        stat = parse_stat((proc_dir / "stat").read_text(encoding="utf-8", errors="replace"))
        status = (proc_dir / "status").read_text(encoding="utf-8", errors="replace")
        io_text = (proc_dir / "io").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    vmrss = parse_status_vmrss_kb(status) or 0
    io = parse_io(io_text)
    read_b = io.get("read_bytes", 0)
    write_b = io.get("write_bytes", 0)
    ticks = stat["cpu_ticks"]
    elapsed = 0.0 if prev is None else max(ts - prev.ts, 0.0)
    sample: dict[str, Any] = {
        "ts": ts,
        "host": host,
        "pid": pid,
        "cpu_pct": 0.0 if prev is None else cpu_pct(prev.cpu_ticks, ticks, elapsed, clk_tck),
        "rss_mb": rss_mb(vmrss),
        "io_read_bps": 0.0 if prev is None else io_bps(prev.read_bytes, read_b, elapsed),
        "io_write_bps": 0.0 if prev is None else io_bps(prev.write_bytes, write_b, elapsed),
    }
    if rank is not None:
        sample["rank"] = rank
    return sample


DiscoverFn = Callable[[], list[ProcInfo]]
SampleFn = Callable[[ProcInfo], dict[str, Any] | None]
SleepFn = Callable[[float], None]
NowFn = Callable[[], float]


def collect_loop(
    *,
    match: str,
    output_dir: Path,
    stop_file: Path,
    interval: float,
    host: str,
    proc_root: Path | None = None,
    collector_pid: int | None = None,
    trailing_samples: int = 2,
    ready_timeout: float = 30.0,
    discoverer: DiscoverFn | None = None,
    sampler: SampleFn | None = None,
    sleep_fn: SleepFn = time.sleep,
    now_fn: NowFn = time.time,
) -> None:
    root = proc_root if proc_root is not None else Path("/proc")
    if discoverer is None:
        def discoverer() -> list[ProcInfo]:
            return discover(root, match, collector_pid)

    prev: dict[int, _Prev] = {}

    def default_sampler(info: ProcInfo) -> dict[str, Any] | None:
        ts = now_fn()
        sample = sample_pid(
            root / str(info.pid),
            host=host,
            pid=info.pid,
            ts=ts,
            prev=prev.get(info.pid),
            rank=info.rank,
        )
        if sample is None:
            return None
        io_dummy_read = 0
        io_dummy_write = 0
        ticks = 0
        try:
            stat = parse_stat((root / str(info.pid) / "stat").read_text(encoding="utf-8", errors="replace"))
            ticks = stat["cpu_ticks"]
            io = parse_io((root / str(info.pid) / "io").read_text(encoding="utf-8", errors="replace"))
            io_dummy_read = io.get("read_bytes", 0)
            io_dummy_write = io.get("write_bytes", 0)
        except OSError:
            pass
        prev[info.pid] = _Prev(
            ts=sample["ts"],
            cpu_ticks=ticks,
            read_bytes=io_dummy_read,
            write_bytes=io_dummy_write,
        )
        return sample

    if sampler is None:
        sampler = default_sampler

    seen = False
    gone = 0
    started = now_fn()
    while True:
        if stop_file.exists():
            return
        infos = discoverer()
        if infos:
            seen = True
            gone = 0
            live = {info.pid for info in infos}
            for info in infos:
                sample = sampler(info)
                if sample is None:
                    continue
                for key in SAMPLE_KEYS:
                    if key not in sample:
                        raise ValueError(f"sample missing {key}")
                append_sample(series_path(output_dir, sample["host"], sample["pid"]), sample)
            prev = {pid: state for pid, state in prev.items() if pid in live}
        else:
            if seen:
                gone += 1
                if gone > trailing_samples:
                    return
            elif now_fn() - started >= ready_timeout:
                return
        sleep_fn(interval)


def run_collect(
    *,
    match: str,
    output_dir: Path,
    stop_file: Path,
    interval: float = 1.0,
    host: str,
    ready_timeout: float = 30.0,
    proc_root: Path | None = None,
) -> int:
    collect_loop(
        match=match,
        output_dir=output_dir,
        stop_file=stop_file,
        interval=interval,
        host=host,
        proc_root=proc_root,
        collector_pid=os.getpid(),
        ready_timeout=ready_timeout,
    )
    return 0
