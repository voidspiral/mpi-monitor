"""Wrap a user command with per-host process collectors."""

from __future__ import annotations

import json
import base64
import io
import os
import shlex
import socket
import subprocess
import sys
import tarfile
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from mpi_monitor.clusterhelm import incident_path_from_env
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
    dest = incident_path_from_env()
    if dest is None:
        return None
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
    connect_timeout = 10 if timeout is None else max(1, int(timeout - 2))
    ssh = [
        "ssh",
        "-T",
        "-n",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={connect_timeout}",
    ]
    if identity:
        ssh += ["-i", identity]
    target = f"{user}@{host}" if user else host
    ssh += [target, remote_command]
    return subprocess.run(ssh, capture_output=True, text=True, timeout=timeout)


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
) -> str:
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
    # Background in a subshell so the SSH login shell can exit. Do not use
    # nohup here: on this cluster `nohup ... &` keeps the SSH session open.
    # setsid + closed stdio is enough for the collector to survive hangup.
    start = (
        f"{mkdir} && (setsid bash -c {shlex.quote(payload)} "
        f">/dev/null 2>{shlex.quote(remote_root + '/collect.err')} </dev/null & "
        f"echo $! >{shlex.quote(remote_root + '/collector.pid')})"
        f" && echo OK"
    )
    result = ssh_run(host, start, user=user, identity=identity, timeout=ready_timeout)
    if getattr(result, "returncode", 0) not in (0, None):
        detail = (getattr(result, "stderr", None) or getattr(result, "stdout", None) or "").strip()
        raise RuntimeError(detail or f"ssh start collector failed: {result.returncode}")
    return remote_root


def _remote_finalize_command(remote_root: str) -> str:
    root = shlex.quote(remote_root)
    stop = shlex.quote(remote_root + "/stop")
    pid_file = shlex.quote(remote_root + "/collector.pid")
    return (
        f"touch {stop}; "
        f"pid=$(cat {pid_file} 2>/dev/null || true); "
        "if [ -n \"$pid\" ]; then "
        "i=0; while kill -0 \"$pid\" 2>/dev/null && [ \"$i\" -lt 50 ]; "
        "do sleep 0.1; i=$((i+1)); done; fi; "
        f"tar -C {root} -cf - series collect.err 2>/dev/null | base64 | tr -d '\\n'"
    )


def _extract_remote_archive(
    encoded: str,
    dest_series: Path,
    *,
    host: str,
) -> None:
    if not encoded.strip():
        return
    payload = base64.b64decode(encoded.strip(), validate=True)
    dest_series.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive.getmembers():
            path = Path(member.name)
            if not member.isfile():
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            if len(path.parts) == 2 and path.parts[0] == "series" and path.suffix == ".jsonl":
                (dest_series / path.name).write_bytes(extracted.read())
            elif path.name == "collect.err" and len(path.parts) == 1:
                (dest_series.parent / f"{host}.collect.err").write_bytes(extracted.read())


def _finalize_remote_series(
    host: str,
    remote_root: str,
    dest_series: Path,
    ssh_run: SshRun,
    *,
    user: str | None,
    identity: str | None,
    timeout: float,
) -> None:
    command = _remote_finalize_command(remote_root)
    failures: list[str] = []
    for attempt, attempt_timeout in enumerate((timeout, max(timeout + 2, timeout * 2)), 1):
        try:
            result = ssh_run(
                host,
                command,
                user=user,
                identity=identity,
                timeout=attempt_timeout,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    (result.stderr or result.stdout or f"ssh exit {result.returncode}").strip()
                )
            _extract_remote_archive(result.stdout, dest_series, host=host)
            return
        except Exception as exc:
            failures.append(f"attempt {attempt}: {exc}")
            if attempt == 1:
                time.sleep(min(0.2, max(0.0, timeout)))
    raise RuntimeError("; ".join(failures))


def join_collectors(handles: Sequence[CollectorHandle], join_timeout: float) -> None:
    deadline = time.monotonic() + join_timeout
    for handle in handles:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            try:
                handle.kill()
            except Exception:
                pass
            continue
        try:
            handle.wait(timeout=remaining)
        except Exception:
            try:
                handle.kill()
            except Exception:
                pass


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
                remote_root = _start_remote_collector(
                    host,
                    run_id=run_id,
                    match=match,
                    interval=interval,
                    ready_timeout=ready_timeout,
                    ssh_run=ssh_run,
                    user=ssh_user,
                    identity=ssh_identity,
                )
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

    try:
        for host, remote_root in remote_roots.items():
            try:
                _finalize_remote_series(
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
            try:
                plot_run(run_dir, run_id=run_id)
            except Exception as exc:
                errors["plot"] = str(exc)
    finally:
        write_meta(
            run_dir,
            {
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "exit_code": exit_code,
                "application_exit_code": exit_code,
                "collection_status": "complete" if not errors else "partial",
                "collect_errors": errors,
            },
        )
    if exit_code != 0 or errors:
        detail = f"exit_code={exit_code}"
        if errors:
            detail += " collect_errors=" + json.dumps(errors)
        write_clusterhelm_incident(
            step="wrap",
            hosts=hosts,
            exit_code=exit_code,
            command=command,
            detail_tail=detail,
            extra={
                "match": match,
                "run_id": run_id,
                "reason_code": (
                    "wrapped_command_failed" if exit_code != 0 else "collection_incomplete"
                ),
            },
        )
    return exit_code
