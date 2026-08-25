"""Plot JSONL series to independently named PNG charts."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

METRICS = ("cpu", "rss", "io_read", "io_write")
METRIC_FIELDS = {
    "cpu": "cpu_pct",
    "rss": "rss_mb",
    "io_read": "io_read_bps",
    "io_write": "io_write_bps",
}

ChartWriter = Callable[[Path, list[float], list[float], str], None]


def chart_filename(run_id: str, host: str, pid: int, metric: str) -> str:
    return f"{run_id}_{host}_pid{pid}_{metric}.png"


def parse_series_filename(name: str) -> tuple[str, int]:
    stem = name[:-6] if name.endswith(".jsonl") else name
    host, sep, pid_s = stem.rpartition("_pid")
    if not sep:
        raise ValueError(f"bad series name: {name}")
    return host, int(pid_s)


def load_samples(path: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            samples.append(obj)
    return samples


def matplotlib_writer(path: Path, xs: list[float], ys: list[float], ylabel: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot(xs, ys)
    ax.set_xlabel("ts")
    ax.set_ylabel(ylabel)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def stub_writer(path: Path, xs: list[float], ys: list[float], ylabel: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PNG")


def plot_run(
    run_dir: Path,
    *,
    run_id: str | None = None,
    writer: ChartWriter | None = None,
    warn_stream: TextIO = sys.stderr,
) -> list[Path]:
    run_id = run_id or run_dir.name
    series_dir = run_dir / "series"
    charts_dir = run_dir / "charts"
    written: list[Path] = []
    if not series_dir.is_dir():
        return written

    if writer is None:
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            print("mpi-monitor: matplotlib not available; skipping PNG charts", file=warn_stream)
            return written
        writer = matplotlib_writer

    for path in sorted(series_dir.glob("*.jsonl")):
        try:
            host, pid = parse_series_filename(path.name)
        except ValueError:
            continue
        samples = load_samples(path)
        if not samples:
            print(f"mpi-monitor: skip empty series {path.name}", file=warn_stream)
            continue
        xs = [float(s.get("ts", 0.0)) for s in samples]
        for metric in METRICS:
            field = METRIC_FIELDS[metric]
            ys = [float(s.get(field, 0.0)) for s in samples]
            out = charts_dir / chart_filename(run_id, host, pid, metric)
            writer(out, xs, ys, field)
            written.append(out)
    return written
