"""Wrap a user command with per-host process collectors."""

from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from mpi_monitor.plot import plot_run
from mpi_monitor.remote import remote_cmd


class CollectorHandle(Protocol):
    def wait(self, timeout: float | None = None) -> int | None: ...

    def kill(self) -> None: ...


RunCommand = Callable[[Sequence[str]], int]
SshRun = Callable[..., subprocess.CompletedProcess[str]]
SpawnLocal = Callable[..., CollectorHandle]


def local_short_name() -> str:
    return socket.gethostname().split(".")[0]


def is_local_host(host: str, local: str | None = None) -> bool:
    local = local or local_short_name()
    short = host.split(".")[0]
    return short == local or host in {"localhost", "127.0.0.1"}


def make_run_id(*, now: datetime | None = None, pid: int | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    pid = os.getpid() if pid is None else pid
    return now.strftime("%Y%m%dT%H%M%SZ") + f"-{pid}"


def write_clusterhelm_incident(
    *,
    step: str,
    hosts: Sequence[str],
    exit_code: int,
    command: Sequence[str],
    detail_tail: str = "",
    extra: dict[str, Any] | None = None,
) -> Path | None:
    """Write ClusterHelm job sidecar when wrap fails. No-op without env."""
    raw = os.environ.get("CLUSTERHELM_INCIDENT_PATH", "").strip()
    if raw:
        dest = Path(raw)
    else:
        job_dir = os.environ.get("AGENT_JOB_DIR", "").strip()
        job_id = os.environ.get("AGENT_JOB_ID", "").strip()
        if not job_dir or not job_id:
            return None
        dest = Path(job_dir) / f"{job_id}.incident.json"
    record: dict[str, Any] = {
        "step": step,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hosts": list(hosts),
        "exit_code": exit_code,
        "command": list(command),
        "detail_tail": (detail_tail or "")[-2000:],
        "source": "mpi-monitor",
    }
    if extra:
        record.update(extra)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    tmp.replace(dest)
    return dest


def write_meta(run_dir: Path, data: dict[str, Any]) -> None:
    path = run_dir / "meta.json"
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    existing.update(data)
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


class SubprocessHandle:
    def __init__(self, proc: subprocess.Popen[str]) -> None:
        self.proc = proc

    def wait(self, timeout: float | None = None) -> int | None:
        return self.proc.wait(timeout=timeout)

    def kill(self) -> None:
        self.proc.kill()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def default_run_command(command: Sequence[str]) -> int:
    return subprocess.call(list(command))


def default_spawn_local(
    *,
    match: str,
    output_dir: Path,
    stop_file: Path,
    interval: float,
    host: str,
    ready_timeout: float,
) -> CollectorHandle:
    cmd = [
        sys.executable,
        "-m",
        "mpi_monitor",
        "collect",
        "--match",
        match,
        "--output-dir",
        str(output_dir),
        "--stop-file",
        str(stop_file),
        "--interval",
        str(interval),
        "--host",
        host,
        "--ready-timeout",
        str(ready_timeout),
    ]
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return SubprocessHandle(proc)


def default_ssh_run(
    host: str,
    remote_command: str,
    *,
    user: str | None = None,
    identity: str | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if identity:
        ssh += ["-i", identity]
    target = f"{user}@{host}" if user else host
    ssh += [target, remote_command]
    return subprocess.run(ssh, capture_output=True, text=True, timeout=timeout)


class SshCollectorHandle:
    def __init__(
        self,
        host: str,
        remote_root: str,
        ssh_run: SshRun,
        *,
        user: str | None,
        identity: str | None,
        join_timeout: float,
    ) -> None:
        self.host = host
        self.remote_root = remote_root
        self.ssh_run = ssh_run
        self.user = user
        self.identity = identity
        self.join_timeout = join_timeout
        self._done = False

    def _ssh(self, command: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
        return self.ssh_run(
            self.host,
            command,
            user=self.user,
            identity=self.identity,
            timeout=timeout,
        )

    def wait(self, timeout: float | None = None) -> int | None:
        if self._done:
            return 0
        limit = self.join_timeout if timeout is None else timeout
        self._ssh(
            f"touch {shlex.quote(self.remote_root + '/stop')}",
            timeout=limit,
        )
        self._done = True
        return 0

    def kill(self) -> None:
        self._ssh(
            f"touch {shlex.quote(self.remote_root + '/stop')}",
            timeout=self.join_timeout,
        )
        self._done = True


def _start_remote_collector(
    host: str,
    *,
    run_id: str,
    match: str,
    interval: float,
    ready_timeout: float,
    ssh_run: SshRun,
    user: str | None,
    identity: str | None,
    join_timeout: float,
) -> tuple[CollectorHandle, str]:
    remote_root = f"/tmp/mpi-monitor/{run_id}/{host}"
    mkdir = f"mkdir -p {shlex.quote(remote_root + '/series')}"
    payload = remote_cmd(
        [
            "collect",
            "--match",
            match,
            "--output-dir",
            remote_root,
            "--stop-file",
            f"{remote_root}/stop",
            "--interval",
            str(interval),
            "--host",
            host,
            "--ready-timeout",
            str(ready_timeout),
        ]
    )
    # background collect on remote; stdout discarded
    start = f"{mkdir} && nohup {payload} >/dev/null 2>{shlex.quote(remote_root + '/collect.err')} &"
    ssh_run(host, start, user=user, identity=identity, timeout=ready_timeout)
    handle = SshCollectorHandle(
        host,
        remote_root,
        ssh_run,
        user=user,
        identity=identity,
        join_timeout=join_timeout,
    )
    return handle, remote_root


def _fetch_remote_series(
    host: str,
    remote_root: str,
    dest_series: Path,
    ssh_run: SshRun,
    *,
    user: str | None,
    identity: str | None,
    timeout: float,
) -> None:
    dest_series.mkdir(parents=True, exist_ok=True)
    listed = ssh_run(
        host,
        f"ls {shlex.quote(remote_root + '/series')} 2>/dev/null || true",
        user=user,
        identity=identity,
        timeout=timeout,
    )
    names = [n for n in listed.stdout.split() if n.endswith(".jsonl")]
    for name in names:
        cat = ssh_run(
            host,
            f"cat {shlex.quote(remote_root + '/series/' + name)}",
            user=user,
            identity=identity,
            timeout=timeout,
        )
        if cat.returncode == 0 and cat.stdout:
            (dest_series / name).write_text(cat.stdout, encoding="utf-8")


def join_collectors(handles: Sequence[CollectorHandle], join_timeout: float) -> None:
    deadline = time.monotonic() + join_timeout
    for handle in handles:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            handle.kill()
            continue
        try:
            handle.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            handle.kill()
        except Exception:
            handle.kill()


def wrap(
    command: Sequence[str],
    *,
    hosts: Sequence[str],
    match: str,
    output_dir: Path,
    interval: float = 1.0,
    ready_timeout: float = 30.0,
    join_timeout: float = 5.0,
    ssh_user: str | None = None,
    ssh_identity: str | None = None,
    local_host: str | None = None,
    run_id: str | None = None,
    run_command: RunCommand | None = None,
    spawn_local: SpawnLocal | None = None,
    ssh_run: SshRun | None = None,
    plot: bool = True,
) -> int:
    if not hosts:
        print("mpi-monitor: --hosts is required", file=sys.stderr)
        return 2
    run_id = run_id or make_run_id()
    run_dir = Path(output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "series").mkdir(exist_ok=True)
    stop_file = run_dir / "stop"
    write_meta(
        run_dir,
        {
            "run_id": run_id,
            "hosts": list(hosts),
            "match": match,
            "command": list(command),
            "interval": interval,
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    run_command = run_command or default_run_command
    spawn_local = spawn_local or default_spawn_local
    ssh_run = ssh_run or default_ssh_run
    local_host = local_host or local_short_name()

    handles: list[CollectorHandle] = []
    remote_roots: dict[str, str] = {}
    errors: dict[str, str] = {}
    for host in hosts:
        try:
            if is_local_host(host, local_host):
                handles.append(
                    spawn_local(
                        match=match,
                        output_dir=run_dir,
                        stop_file=stop_file,
                        interval=interval,
                        host=host.split(".")[0],
                        ready_timeout=ready_timeout,
                    )
                )
            else:
                handle, remote_root = _start_remote_collector(
                    host,
                    run_id=run_id,
                    match=match,
                    interval=interval,
                    ready_timeout=ready_timeout,
                    ssh_run=ssh_run,
                    user=ssh_user,
                    identity=ssh_identity,
                    join_timeout=join_timeout,
                )
                handles.append(handle)
                remote_roots[host] = remote_root
        except Exception as exc:
            errors[host] = str(exc)
            print(f"mpi-monitor: collect error on {host}: {exc}", file=sys.stderr)

    try:
        exit_code = run_command(command)
    except Exception as exc:
        exit_code = 1
        print(f"mpi-monitor: command failed to start: {exc}", file=sys.stderr)
    stop_file.touch()
    join_collectors(handles, join_timeout)

    for host, remote_root in remote_roots.items():
        try:
            _fetch_remote_series(
                host,
                remote_root,
                run_dir / "series",
                ssh_run,
                user=ssh_user,
                identity=ssh_identity,
                timeout=join_timeout,
            )
        except Exception as exc:
            errors[host] = str(exc)

    if plot:
        plot_run(run_dir, run_id=run_id)

    write_meta(
        run_dir,
        {
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "exit_code": exit_code,
            "collect_errors": errors,
        },
    )
    if exit_code != 0:
        detail = f"exit_code={exit_code}"
        if errors:
            detail += " collect_errors=" + json.dumps(errors)
        write_clusterhelm_incident(
            step="wrap",
            hosts=hosts,
            exit_code=exit_code,
            command=command,
            detail_tail=detail,
            extra={"match": match, "run_id": run_id},
        )
    return exit_code
