"""ClusterHelm job JSON path and CLI hard-gate helpers."""

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
from unittest import mock

from mpi_monitor.cli import main
from mpi_monitor.clusterhelm import (
    incident_path_from_env,
    job_json_path,
    resolve_cli_argv,
)


REPO = Path(__file__).resolve().parents[1]


class TestJobJsonPath(unittest.TestCase):
    def test_job_json_is_sibling_file_not_nested_dir(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        jobs = Path(tmp.name)
        job_id = "job-20260828T001848Z-1931"
        expected = jobs / f"{job_id}.json"
        expected.write_text("{}", encoding="utf-8")
        nested_wrong = jobs / job_id / f"{job_id}.json"
        path = job_json_path(job_dir=str(jobs), job_id=job_id)
        self.assertEqual(path, expected)
        self.assertNotEqual(path, nested_wrong)
        self.assertTrue(path.is_file())
        self.assertFalse(nested_wrong.exists())
        tmp.cleanup()

    def test_job_json_reads_agent_env(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        jobs = Path(tmp.name)
        job_id = "job-x"
        (jobs / f"{job_id}.json").write_text("{}", encoding="utf-8")
        env = {"AGENT_JOB_DIR": str(jobs), "AGENT_JOB_ID": job_id}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(job_json_path(), jobs / f"{job_id}.json")
        tmp.cleanup()

    def test_missing_env_raises(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_JOB_DIR": "", "AGENT_JOB_ID": ""}, clear=False):
            with self.assertRaises(ValueError):
                job_json_path()

    def test_cli_job_json_prints_flat_path(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        jobs = Path(tmp.name)
        job_id = "job-cli"
        target = jobs / f"{job_id}.json"
        target.write_text("{}", encoding="utf-8")
        buf = __import__("io").StringIO()
        env = {"AGENT_JOB_DIR": str(jobs), "AGENT_JOB_ID": job_id}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch("sys.stdout", buf):
            code = main(["job-json"])
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue().strip(), str(target))
        tmp.cleanup()

    def test_cli_job_json_require_missing_exits_2(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        env = {"AGENT_JOB_DIR": tmp.name, "AGENT_JOB_ID": "missing-job"}
        with mock.patch.dict(os.environ, env, clear=False):
            code = main(["job-json", "--require"])
        self.assertEqual(code, 2)
        tmp.cleanup()

    def test_incident_path_matches_job_json_stem(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        jobs = Path(tmp.name)
        env = {
            "AGENT_JOB_DIR": str(jobs),
            "AGENT_JOB_ID": "job-inc",
            "CLUSTERHELM_INCIDENT_PATH": "",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(
                incident_path_from_env(),
                jobs / "job-inc.incident.json",
            )
        tmp.cleanup()


class TestResolveCliArgv(unittest.TestCase):
    def test_path_binary_is_single_token(self) -> None:
        argv = resolve_cli_argv(
            vendor_root=REPO,
            which=lambda _name: "/usr/bin/mpi-monitor",
        )
        self.assertEqual(argv, ["/usr/bin/mpi-monitor"])

    def test_python_module_is_argv_list_not_one_string(self) -> None:
        argv = resolve_cli_argv(
            vendor_root=REPO,
            which=lambda _name: None,
            venv_bin=Path("/no/such/venv/mpi-monitor"),
        )
        self.assertIsInstance(argv, list)
        self.assertGreater(len(argv), 1)
        self.assertNotIn(" ", argv[0])
        self.assertIn("-m", argv)
        self.assertIn("mpi_monitor", argv)

    def test_cli_probe_ok(self) -> None:
        buf = __import__("io").StringIO()
        with mock.patch("sys.stdout", buf):
            code = main(["probe"])
        self.assertEqual(code, 0)
        self.assertIn("ok", buf.getvalue())


class TestProbeCliScript(unittest.TestCase):
    def test_quoted_multiword_command_is_no_such_file(self) -> None:
        result = subprocess.run(
            [
                "bash",
                "-c",
                'MPI_MON="python3 -m mpi_monitor"; "$MPI_MON" probe',
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        combined = result.stderr + result.stdout
        self.assertTrue(
            "No such file" in combined or "command not found" in combined,
            combined,
        )

    def test_probe_script_uses_array_and_succeeds(self) -> None:
        env = os.environ.copy()
        env["MPI_MONITOR_VENDOR"] = str(REPO)
        path_parts = [p for p in env.get("PATH", "").split(":") if p and "mpi-monitor" not in p]
        env["PATH"] = ":".join(path_parts)
        result = subprocess.run(
            ["bash", str(REPO / "scripts" / "probe-cli.sh")],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO),
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("HARD_GATE: OK", result.stdout)
        payload = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertIsInstance(payload["argv"], list)
        self.assertTrue(payload["argv"])
        self.assertNotIn(" ", payload["argv"][0])


if __name__ == "__main__":
    unittest.main()
