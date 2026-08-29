"""Local vs remote host routing for wrap."""

from __future__ import annotations

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "src"))


import json
import base64
import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from mpi_monitor.wrap import default_ssh_run, is_local_host, wrap


class _DoneHandle:
    def wait(self, timeout: float | None = None) -> int:
        return 0

    def kill(self) -> None:
        return None


class TestWrapHosts(unittest.TestCase):
    @staticmethod
    def _series_archive(name: str = "cn2_pid1.jsonl") -> str:
        payload = b'{"host":"cn2","pid":1}\n'
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as archive:
            info = tarfile.TarInfo(f"series/{name}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        return base64.b64encode(stream.getvalue()).decode()

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
        self.assertIn("</dev/null &", start)
        self.assertIn("collector.pid", start)
        self.assertIn("echo OK", start)
        self.assertNotIn("nohup", start)
        tmp.cleanup()

    def test_remote_stop_and_fetch_use_one_transaction(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        calls: list[tuple[str, float | None]] = []

        def ssh_run(host, command, **kwargs):
            calls.append((command, kwargs.get("timeout")))
            stdout = self._series_archive() if "base64" in command else "OK\n"
            return subprocess.CompletedProcess(["ssh"], 0, stdout=stdout, stderr="")

        code = wrap(
            ["true"],
            hosts=["cn2"],
            match="job",
            output_dir=Path(tmp.name),
            local_host="cn1",
            run_command=lambda _c: 0,
            spawn_local=lambda **_k: _DoneHandle(),
            ssh_run=ssh_run,
            plot=False,
            join_timeout=5,
            run_id="run-one-transaction",
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 2)
        finalize = calls[1][0]
        self.assertIn("touch ", finalize)
        self.assertIn("tar -C", finalize)
        self.assertIn("base64", finalize)
        self.assertNotIn("ls ", finalize)
        self.assertNotIn("/series/", finalize)
        series = Path(tmp.name) / "run-one-transaction/series/cn2_pid1.jsonl"
        self.assertTrue(series.is_file())
        tmp.cleanup()

    def test_remote_timeout_is_partial_and_meta_is_always_finalized(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        commands: list[str] = []

        def ssh_run(host, command, **kwargs):
            commands.append(command)
            if "setsid bash -c" in command:
                return subprocess.CompletedProcess(["ssh"], 0, stdout="OK\n", stderr="")
            raise subprocess.TimeoutExpired(["ssh"], kwargs.get("timeout"))

        code = wrap(
            ["true"],
            hosts=["cn2"],
            match="job",
            output_dir=Path(tmp.name),
            local_host="cn1",
            run_command=lambda _c: 0,
            spawn_local=lambda **_k: _DoneHandle(),
            ssh_run=ssh_run,
            plot=False,
            join_timeout=0.01,
            run_id="run-timeout",
        )
        self.assertEqual(code, 0)
        meta = json.loads((Path(tmp.name) / "run-timeout/meta.json").read_text())
        self.assertEqual(meta["application_exit_code"], 0)
        self.assertEqual(meta["collection_status"], "partial")
        self.assertIn("cn2", meta["collect_errors"])
        self.assertIn("ended_at", meta)
        self.assertEqual(sum("touch " in command for command in commands), 2)
        tmp.cleanup()

    def test_default_ssh_outer_timeout_exceeds_connect_timeout(self) -> None:
        with mock.patch("mpi_monitor.wrap.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(["ssh"], 0, "", "")
            default_ssh_run("cn2", "true", timeout=5)
        argv = run.call_args.args[0]
        connect = int(argv[argv.index("ConnectTimeout=3")].split("=", 1)[1])
        self.assertLess(connect, run.call_args.kwargs["timeout"])

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
