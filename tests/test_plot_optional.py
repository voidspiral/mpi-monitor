"""Plotting is optional when matplotlib is missing."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mpi_monitor.plot import plot_run


class TestPlotOptional(unittest.TestCase):
    def test_missing_matplotlib_warns_and_keeps_jsonl(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        run = Path(tmp.name) / "r1"
        series = run / "series"
        series.mkdir(parents=True)
        sample = {
            "ts": 1,
            "host": "h",
            "pid": 1,
            "cpu_pct": 1,
            "rss_mb": 1,
            "io_read_bps": 0,
            "io_write_bps": 0,
        }
        jsonl = series / "h_pid1.jsonl"
        jsonl.write_text(json.dumps(sample) + "\n", encoding="utf-8")
        err = io.StringIO()
        with mock.patch.dict("sys.modules", {"matplotlib": None}):
            # Force ImportError on import matplotlib
            import builtins

            real_import = builtins.__import__

            def fake_import(name, *args, **kwargs):
                if name == "matplotlib" or name.startswith("matplotlib."):
                    raise ImportError("no matplotlib")
                return real_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", fake_import):
                written = plot_run(run, run_id="r1", warn_stream=err)
        self.assertEqual(written, [])
        self.assertTrue(jsonl.exists())
        self.assertIn("matplotlib", err.getvalue())
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
