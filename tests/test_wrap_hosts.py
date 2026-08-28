"""Local vs remote host routing for wrap."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from mpi_monitor.wrap import is_local_host, wrap


class _DoneHandle:
    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        return None


class TestWrapHosts(unittest.TestCase):
    def test_localhost_aliases_are_local(self) -> None:
        self.assertTrue(is_local_host("localhost", local="cn1"))
        self.assertTrue(is_local_host("cn1", local="cn1"))
        self.assertTrue(is_local_host("cn1.cluster", local="cn1"))
        self.assertFalse(is_local_host("cn2", local="cn1"))

    def test_local_host_does_not_ssh(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        ssh_calls: list[tuple] = []
        local_calls: list[str] = []

        def spawn_local(**kwargs):
            local_calls.append(kwargs["host"])
            return _DoneHandle()

        def ssh_run(host, command, **kwargs):
            ssh_calls.append((host, command))
            return subprocess.CompletedProcess(["ssh"], 0, stdout="", stderr="")

        code = wrap(
            ["true"],
            hosts=["cn1"],
            match="job",
            output_dir=Path(tmp.name),
            local_host="cn1",
            run_command=lambda _c: 0,
            spawn_local=spawn_local,
            ssh_run=ssh_run,
            plot=False,
            join_timeout=0.2,
        )
        self.assertEqual(code, 0)
        self.assertEqual(local_calls, ["cn1"])
        self.assertEqual(ssh_calls, [])
        tmp.cleanup()

    def test_remote_host_uses_ssh_helper(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        ssh_calls: list[str] = []

        def spawn_local(**kwargs):
            raise AssertionError("should not spawn local")

        def ssh_run(host, command, **kwargs):
            ssh_calls.append(host)
            stdout = ""
            if "ls " in command:
                stdout = ""
            return subprocess.CompletedProcess(["ssh"], 0, stdout=stdout, stderr="")

        code = wrap(
            ["true"],
            hosts=["cn2"],
            match="job",
            output_dir=Path(tmp.name),
            local_host="cn1",
            run_command=lambda _c: 0,
            spawn_local=spawn_local,
            ssh_run=ssh_run,
            plot=False,
            join_timeout=0.5,
            run_id="run-test",
        )
        self.assertEqual(code, 0)
        self.assertIn("cn2", ssh_calls)
        tmp.cleanup()

    def test_remote_start_detaches_ssh_session(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        commands: list[str] = []

        def spawn_local(**kwargs):
            raise AssertionError("should not spawn local")

        def ssh_run(host, command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(["ssh"], 0, stdout="", stderr="")

        code = wrap(
            ["true"],
            hosts=["cn2"],
            match="job",
            output_dir=Path(tmp.name),
            local_host="cn1",
            run_command=lambda _c: 0,
            spawn_local=spawn_local,
            ssh_run=ssh_run,
            plot=False,
            join_timeout=0.2,
            run_id="run-detach",
        )
        self.assertEqual(code, 0)
        start = next(c for c in commands if "setsid bash -c" in c)
        self.assertIn("(setsid bash -c", start)
        self.assertIn("</dev/null &)", start)
        self.assertIn("echo OK", start)
        self.assertNotIn("nohup", start)
        tmp.cleanup()

    def test_nonzero_exit_writes_incident_sidecar(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        inc = Path(tmp.name) / "job.incident.json"
        previous = os.environ.get("CLUSTERHELM_INCIDENT_PATH")
        os.environ["CLUSTERHELM_INCIDENT_PATH"] = str(inc)
        try:
            code = wrap(
                ["mpirun", "-np", "2", "is.W.x"],
                hosts=["cn1", "cn2"],
                match="is.W.x",
                output_dir=Path(tmp.name) / "out",
                local_host="cn1",
                run_command=lambda _c: 255,
                spawn_local=lambda **_k: _DoneHandle(),
                ssh_run=lambda host, command, **kwargs: subprocess.CompletedProcess(
                    ["ssh"], 0, stdout="", stderr=""
                ),
                plot=False,
                join_timeout=0.2,
            )
            self.assertEqual(code, 255)
            data = json.loads(inc.read_text())
            self.assertEqual(data["step"], "wrap")
            self.assertEqual(data["exit_code"], 255)
            self.assertEqual(data["source"], "mpi-monitor")
            self.assertEqual(data["hosts"], ["cn1", "cn2"])
        finally:
            if previous is None:
                os.environ.pop("CLUSTERHELM_INCIDENT_PATH", None)
            else:
                os.environ["CLUSTERHELM_INCIDENT_PATH"] = previous
            tmp.cleanup()

    def test_zero_exit_does_not_write_incident(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        inc = Path(tmp.name) / "job.incident.json"
        previous = os.environ.get("CLUSTERHELM_INCIDENT_PATH")
        os.environ["CLUSTERHELM_INCIDENT_PATH"] = str(inc)
        try:
            code = wrap(
                ["true"],
                hosts=["cn1"],
                match="job",
                output_dir=Path(tmp.name) / "out",
                local_host="cn1",
                run_command=lambda _c: 0,
                spawn_local=lambda **_k: _DoneHandle(),
                ssh_run=lambda host, command, **kwargs: subprocess.CompletedProcess(
                    ["ssh"], 0, stdout="", stderr=""
                ),
                plot=False,
                join_timeout=0.2,
            )
            self.assertEqual(code, 0)
            self.assertFalse(inc.is_file())
        finally:
            if previous is None:
                os.environ.pop("CLUSTERHELM_INCIDENT_PATH", None)
            else:
                os.environ["CLUSTERHELM_INCIDENT_PATH"] = previous
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
