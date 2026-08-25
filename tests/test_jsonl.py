"""JSONL schema and series naming tests."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import json
import tempfile
import unittest
from pathlib import Path

from mpi_monitor.collect import SAMPLE_KEYS, collect_loop, series_filename
from mpi_monitor.discover import ProcInfo


class TestJsonl(unittest.TestCase):
    def test_series_filename(self) -> None:
        self.assertEqual(series_filename("cn1", 42), "cn1_pid42.jsonl")

    def test_collect_writes_required_keys_and_per_pid_files(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        out = Path(tmp.name)
        stop = out / "stop"
        infos = [
            ProcInfo(pid=7, comm="a", cmdline="a"),
            ProcInfo(pid=8, comm="b", cmdline="b"),
        ]
        calls = {"n": 0}

        def discoverer() -> list[ProcInfo]:
            calls["n"] += 1
            if calls["n"] == 1:
                return infos
            return []

        def sampler(info: ProcInfo) -> dict:
            return {
                "ts": 1.5,
                "host": "cn1",
                "pid": info.pid,
                "cpu_pct": 10.0,
                "rss_mb": 2.0,
                "io_read_bps": 3.0,
                "io_write_bps": 4.0,
            }

        collect_loop(
            match="a",
            output_dir=out,
            stop_file=stop,
            interval=0.01,
            host="cn1",
            discoverer=discoverer,
            sampler=sampler,
            sleep_fn=lambda _s: None,
            trailing_samples=0,
            ready_timeout=0.0,
        )
        paths = sorted((out / "series").glob("*.jsonl"))
        self.assertEqual([p.name for p in paths], ["cn1_pid7.jsonl", "cn1_pid8.jsonl"])
        for path in paths:
            rows = [json.loads(line) for line in path.read_text().splitlines() if line]
            self.assertGreaterEqual(len(rows), 1)
            for key in SAMPLE_KEYS:
                self.assertIn(key, rows[0])
            self.assertIsInstance(rows[0]["cpu_pct"], (int, float))
            self.assertIsInstance(rows[0]["rss_mb"], (int, float))
            self.assertIsInstance(rows[0]["io_read_bps"], (int, float))
            self.assertIsInstance(rows[0]["io_write_bps"], (int, float))
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
