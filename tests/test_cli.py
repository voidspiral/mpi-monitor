"""CLI wrap / remote-cmd tests."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import base64
import io
import json
import os
import socket
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from mpi_monitor.cli import main
from mpi_monitor.remote import remote_cmd


class TestCli(unittest.TestCase):
    def test_wrap_without_hosts_exits_nonzero(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            main(["wrap", "--match", "x", "--output-dir", "/tmp", "--", "true"])
        self.assertNotEqual(ctx.exception.code, 0)

    def test_remote_cmd_stdout_is_decodable_python_payload(self) -> None:
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            code = main(["remote-cmd"])
        self.assertEqual(code, 0)
        line = buf.getvalue().strip()
        self.assertIn("base64 -d", line)
        inner = line.split()[1]
        boot = base64.b64decode(inner).decode("utf-8")
        self.assertIn("from mpi_monitor.cli import main", boot)
        marker = "b64decode('"
        start = boot.index(marker) + len(marker)
        end = boot.index("')", start)
        raw = base64.b64decode(boot[start:end])
        names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
        self.assertIn("mpi_monitor/cli.py", names)
        # also the helper returns the same shape
        self.assertIn("base64 -d", remote_cmd())

    def test_local_wrap_writes_series_and_preserves_exit_code(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        out = Path(tmp.name)
        host = socket.gethostname().split(".")[0]
        marker = f"MPI_MONITOR_WRAP_{os.getpid()}"
        script = Path(tmp.name) / marker
        script.write_text(
            "#!/usr/bin/env python3\nimport time, sys\ntime.sleep(0.35)\nsys.exit(7)\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        code = main(
            [
                "wrap",
                "--hosts",
                host,
                "--match",
                marker,
                "--output-dir",
                str(out),
                "--interval",
                "0.05",
                "--join-timeout",
                "3",
                "--ready-timeout",
                "2",
                "--",
                str(script),
            ]
        )
        self.assertEqual(code, 7)
        runs = [p for p in out.iterdir() if p.is_dir()]
        self.assertEqual(len(runs), 1)
        series = list((runs[0] / "series").glob("*.jsonl"))
        self.assertGreaterEqual(len(series), 1)
        row = json.loads(series[0].read_text().splitlines()[0])
        for key in ("ts", "host", "pid", "cpu_pct", "rss_mb", "io_read_bps", "io_write_bps"):
            self.assertIn(key, row)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
