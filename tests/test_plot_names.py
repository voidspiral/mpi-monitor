"""PNG filename and per-process chart tests."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import tempfile
import unittest
from pathlib import Path

from mpi_monitor.plot import METRICS, chart_filename, plot_run, stub_writer


class TestPlotNames(unittest.TestCase):
    def test_chart_filename(self) -> None:
        name = chart_filename("run1", "cn2", 99, "cpu")
        self.assertEqual(name, "run1_cn2_pid99_cpu.png")

    def test_four_charts_per_process_no_overlay(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        run = Path(tmp.name) / "jobA"
        series = run / "series"
        series.mkdir(parents=True)
        for host, pid in (("cn1", 10), ("cn2", 11)):
            (series / f"{host}_pid{pid}.jsonl").write_text(
                '{"ts":1,"host":"%s","pid":%d,"cpu_pct":1,"rss_mb":2,"io_read_bps":3,"io_write_bps":4}\n'
                % (host, pid),
                encoding="utf-8",
            )
        written = plot_run(run, run_id="jobA", writer=stub_writer)
        names = sorted(p.name for p in written)
        expected = [
            chart_filename("jobA", host, pid, metric)
            for host, pid in (("cn1", 10), ("cn2", 11))
            for metric in METRICS
        ]
        self.assertEqual(names, sorted(expected))
        self.assertEqual(len(written), 8)
        tmp.cleanup()

    def test_empty_series_skipped(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        run = Path(tmp.name) / "jobB"
        series = run / "series"
        series.mkdir(parents=True)
        (series / "cn1_pid5.jsonl").write_text("", encoding="utf-8")
        written = plot_run(run, run_id="jobB", writer=stub_writer)
        self.assertEqual(written, [])
        self.assertFalse((run / "charts").exists() and any((run / "charts").iterdir()))
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
