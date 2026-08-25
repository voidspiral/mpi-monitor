"""Collector lifetime: PID gone trailing samples and stop file."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import tempfile
import unittest
from pathlib import Path

from mpi_monitor.collect import collect_loop
from mpi_monitor.discover import ProcInfo


class TestCollectLifecycle(unittest.TestCase):
    def test_exits_after_two_extra_intervals_when_pids_gone(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        out = Path(tmp.name)
        stop = out / "stop"
        cycles = {"n": 0}
        sleeps: list[float] = []

        def discoverer() -> list[ProcInfo]:
            cycles["n"] += 1
            if cycles["n"] <= 2:
                return [ProcInfo(pid=1, comm="job", cmdline="job")]
            return []

        def sampler(_info: ProcInfo) -> dict:
            return {
                "ts": float(cycles["n"]),
                "host": "h",
                "pid": 1,
                "cpu_pct": 1.0,
                "rss_mb": 1.0,
                "io_read_bps": 0.0,
                "io_write_bps": 0.0,
            }

        collect_loop(
            match="job",
            output_dir=out,
            stop_file=stop,
            interval=0.05,
            host="h",
            discoverer=discoverer,
            sampler=sampler,
            sleep_fn=lambda s: sleeps.append(s),
            trailing_samples=2,
            ready_timeout=100.0,
        )
        empty_cycles = cycles["n"] - 2
        self.assertLessEqual(empty_cycles, 3)
        self.assertGreaterEqual(empty_cycles, 2)
        self.assertLessEqual(len(sleeps), 4)
        tmp.cleanup()

    def test_stop_file_exits_immediately(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        out = Path(tmp.name)
        stop = out / "stop"
        stop.touch()
        called = {"n": 0}

        def discoverer() -> list[ProcInfo]:
            called["n"] += 1
            return [ProcInfo(pid=1, comm="job", cmdline="job")]

        collect_loop(
            match="job",
            output_dir=out,
            stop_file=stop,
            interval=0.01,
            host="h",
            discoverer=discoverer,
            sampler=lambda _i: None,
            sleep_fn=lambda _s: None,
            ready_timeout=100.0,
        )
        self.assertEqual(called["n"], 0)
        self.assertFalse((out / "series").exists())
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
