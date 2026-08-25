"""Failing fixtures for /proc parse (task 2.1)."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import unittest

from mpi_monitor.proc import cpu_pct, io_bps, parse_io, parse_stat, parse_status_vmrss_kb, rss_mb

STAT = (
    "4242 (is.S.x) R 1 1 1 0 -1 4194304 0 0 0 0 50 25 0 0 20 0 "
    "1 0 12345 12345678 100 18446744073709551615 0 0 0 0 0 0 0 0 0 0 0 0 17 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n"
)

STATUS = """Name:\tis.S.x
State:\tR (running)
Pid:\t4242
VmRSS:\t  2048 kB
VmSize:\t  8192 kB
"""

IO = """rchar: 10
wchar: 20
syscr: 1
syscw: 2
read_bytes: 4096
write_bytes: 8192
cancelled_write_bytes: 0
"""


class TestProcParse(unittest.TestCase):
    def test_parse_stat_cpu_ticks(self) -> None:
        parsed = parse_stat(STAT)
        self.assertEqual(parsed["pid"], 4242)
        self.assertEqual(parsed["comm"], "is.S.x")
        self.assertEqual(parsed["utime"], 50)
        self.assertEqual(parsed["stime"], 25)
        self.assertEqual(parsed["cpu_ticks"], 75)

    def test_cpu_pct_from_tick_delta(self) -> None:
        self.assertAlmostEqual(
            cpu_pct(prev_ticks=75, curr_ticks=175, elapsed_sec=1.0, clk_tck=100),
            100.0,
        )
        self.assertEqual(cpu_pct(prev_ticks=10, curr_ticks=10, elapsed_sec=1.0, clk_tck=100), 0.0)
        self.assertEqual(cpu_pct(prev_ticks=10, curr_ticks=20, elapsed_sec=0.0, clk_tck=100), 0.0)

    def test_parse_status_vmrss_and_rss_mb(self) -> None:
        self.assertEqual(parse_status_vmrss_kb(STATUS), 2048)
        self.assertAlmostEqual(rss_mb(2048), 2.0)

    def test_parse_io_and_rates(self) -> None:
        parsed = parse_io(IO)
        self.assertEqual(parsed["read_bytes"], 4096)
        self.assertEqual(parsed["write_bytes"], 8192)
        self.assertAlmostEqual(io_bps(prev=4096, curr=8192, elapsed_sec=2.0), 2048.0)
        self.assertEqual(io_bps(prev=1, curr=2, elapsed_sec=0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
