"""Wrap join is bounded after the user command returns."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from mpi_monitor.wrap import wrap


class HangHandle:
    def __init__(self) -> None:
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        if timeout is None:
            time.sleep(30)
            return 0
        time.sleep(min(timeout, 0.05))
        raise subprocess.TimeoutExpired(cmd="collect", timeout=timeout)

    def kill(self) -> None:
        self.killed = True


class TestWrapStop(unittest.TestCase):
    def test_join_is_bounded_and_stop_file_written(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        handle = HangHandle()
        started = time.monotonic()
        code = wrap(
            ["true"],
            hosts=["cn1"],
            match="job",
            output_dir=Path(tmp.name),
            local_host="cn1",
            run_command=lambda _c: 0,
            spawn_local=lambda **_k: handle,
            plot=False,
            join_timeout=0.3,
            run_id="stop-test",
        )
        elapsed = time.monotonic() - started
        self.assertEqual(code, 0)
        self.assertLess(elapsed, 2.0)
        self.assertTrue(handle.killed)
        stop = Path(tmp.name) / "stop-test" / "stop"
        self.assertTrue(stop.exists())
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
