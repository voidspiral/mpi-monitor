"""Process discovery match/exclude tests."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import tempfile
import unittest
from pathlib import Path

from mpi_monitor.discover import EXCLUDE_COMM, discover


def _write_proc(
    root: Path,
    pid: int,
    comm: str,
    cmdline: str,
    environ: bytes | None = None,
) -> None:
    d = root / str(pid)
    d.mkdir()
    (d / "comm").write_text(comm + "\n", encoding="utf-8")
    payload = cmdline.encode("utf-8")
    if not payload.endswith(b"\x00"):
        payload += b"\x00"
    (d / "cmdline").write_bytes(payload)
    if environ is not None:
        (d / "environ").write_bytes(environ)


class TestDiscover(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_selects_rank_binary(self) -> None:
        _write_proc(self.root, 10, "is.S.x", "/home/NPB/bin/is.S.x")
        _write_proc(self.root, 11, "mpirun", "mpirun -np 2 is.S.x")
        found = discover(self.root, "is.S.x", collector_pid=99)
        self.assertEqual([p.pid for p in found], [10])
        self.assertEqual(found[0].comm, "is.S.x")

    def test_excludes_launchers_even_if_match_appears(self) -> None:
        for i, comm in enumerate(sorted(EXCLUDE_COMM), start=20):
            _write_proc(self.root, i, comm, f"{comm} --foo is.S.x")
        _write_proc(self.root, 9, "is.S.x", "is.S.x")
        found = discover(self.root, "is.S.x", collector_pid=1)
        self.assertEqual([p.pid for p in found], [9])

    def test_excludes_collector_pid(self) -> None:
        _write_proc(self.root, 50, "python3", "python3 -m mpi_monitor collect --match is.S.x")
        _write_proc(self.root, 51, "is.S.x", "is.S.x")
        found = discover(self.root, "is.S.x", collector_pid=50)
        self.assertEqual([p.pid for p in found], [51])

    def test_match_is_executable_not_later_argv(self) -> None:
        _write_proc(
            self.root,
            10,
            "python3",
            "python3 -m mpi_monitor wrap --match is.S.x -- mpirun /home/NPB/bin/is.S.x",
        )
        _write_proc(
            self.root,
            11,
            "python3",
            "python3 - collect --match is.S.x --output-dir /tmp/x",
        )
        _write_proc(self.root, 12, "ssh", "ssh cn2 python3 - collect --match is.S.x")
        _write_proc(self.root, 9, "is.S.x", "/home/NPB/bin/is.S.x arg")
        found = discover(self.root, "is.S.x", collector_pid=1)
        self.assertEqual([p.pid for p in found], [9])

    def test_shebang_script_matches_argv1(self) -> None:
        marker = "MPI_MONITOR_WRAP_1"
        _write_proc(
            self.root,
            9,
            "python3",
            f"/usr/bin/python3 /tmp/{marker}",
        )
        _write_proc(
            self.root,
            10,
            "python3",
            f"python3 -m mpi_monitor wrap --match {marker} -- /tmp/{marker}",
        )
        found = discover(self.root, marker, collector_pid=1)
        self.assertEqual([p.pid for p in found], [9])


if __name__ == "__main__":
    unittest.main()
