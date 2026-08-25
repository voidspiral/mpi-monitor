"""MPI rank environment parsing tests."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import tempfile
import unittest
from pathlib import Path

from mpi_monitor.discover import discover, parse_rank_environ


def _env(*pairs: tuple[str, str]) -> bytes:
    return b"\x00".join(f"{k}={v}".encode() for k, v in pairs) + b"\x00"


class TestRank(unittest.TestCase):
    def test_pmix_first(self) -> None:
        data = _env(("PMIX_RANK", "3"), ("PMI_RANK", "9"))
        self.assertEqual(parse_rank_environ(data), 3)

    def test_ompi(self) -> None:
        self.assertEqual(parse_rank_environ(_env(("OMPI_COMM_WORLD_RANK", "1"))), 1)

    def test_pmi(self) -> None:
        self.assertEqual(parse_rank_environ(_env(("PMI_RANK", "7"))), 7)

    def test_absent(self) -> None:
        self.assertIsNone(parse_rank_environ(_env(("HOME", "/tmp"))))
        self.assertIsNone(parse_rank_environ(b""))

    def test_discover_attaches_rank(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        d = root / "12"
        d.mkdir()
        (d / "comm").write_text("is.S.x\n")
        (d / "cmdline").write_bytes(b"is.S.x\x00")
        (d / "environ").write_bytes(_env(("PMI_RANK", "4")))
        d2 = root / "13"
        d2.mkdir()
        (d2 / "comm").write_text("is.S.x\n")
        (d2 / "cmdline").write_bytes(b"is.S.x\x00")
        (d2 / "environ").write_bytes(_env(("HOME", "/tmp")))
        found = {p.pid: p for p in discover(root, "is.S.x")}
        self.assertEqual(found[12].rank, 4)
        self.assertIsNone(found[13].rank)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
