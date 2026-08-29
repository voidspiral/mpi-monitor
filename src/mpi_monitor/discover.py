"""Discover MPI/task PIDs from a /proc tree."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EXCLUDE_COMM = {
    "mpirun",
    "mpiexec",
    "orted",
    "orterun",
    "prted",
    "prterun",
    "sshd",
    "ssh",
    "hydra_pmi_proxy",
}

RANK_ENV_KEYS = ("PMIX_RANK", "OMPI_COMM_WORLD_RANK", "PMI_RANK")

# argv1 may be the script when argv0 is an interpreter (shebang).
_INTERPRETER_NAMES = {"bash", "sh", "dash", "perl", "ruby"}
_INTERPRETER_SKIP_NEXT = {"-c", "-m"}


@dataclass(frozen=True)
class ProcInfo:
    pid: int
    comm: str
    cmdline: str
    rank: int | None = None


def read_cmdline(proc_dir: Path) -> str:
    raw = (proc_dir / "cmdline").read_bytes()
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()


def read_comm(proc_dir: Path) -> str:
    text = (proc_dir / "comm").read_text(encoding="utf-8", errors="replace").strip()
    return text


def parse_rank_environ(data: bytes) -> int | None:
    env: dict[str, str] = {}
    for item in data.split(b"\x00"):
        if not item or b"=" not in item:
            continue
        key, _, value = item.partition(b"=")
        try:
            env[key.decode("utf-8")] = value.decode("utf-8", "replace")
        except UnicodeDecodeError:
            continue
    for name in RANK_ENV_KEYS:
        if name in env and env[name] != "":
            try:
                return int(env[name])
            except ValueError:
                continue
    return None


def read_rank(proc_dir: Path) -> int | None:
    path = proc_dir / "environ"
    try:
        return parse_rank_environ(path.read_bytes())
    except OSError:
        return None


def should_exclude(comm: str, pid: int, collector_pid: int | None) -> bool:
    if collector_pid is not None and pid == collector_pid:
        return True
    return comm in EXCLUDE_COMM


def _exe_basename(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _is_interpreter(token: str) -> bool:
    name = _exe_basename(token)
    return name.startswith("python") or name in _INTERPRETER_NAMES


def cmdline_matches(cmdline: str, match: str, comm: str = "") -> bool:
    """Match the rank executable (comm, argv0, or shebang argv1), not later argv."""
    if not match:
        return False
    if comm and match in comm:
        return True
    tokens = cmdline.split()
    if not tokens:
        return False
    if match in tokens[0]:
        return True
    if (
        len(tokens) >= 2
        and _is_interpreter(tokens[0])
        and tokens[1] not in _INTERPRETER_SKIP_NEXT
        and match in tokens[1]
    ):
        return True
    return False


def discover(
    proc_root: Path,
    match: str,
    collector_pid: int | None = None,
) -> list[ProcInfo]:
    found: list[ProcInfo] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            comm = read_comm(entry)
            cmdline = read_cmdline(entry)
        except OSError:
            continue
        if should_exclude(comm, pid, collector_pid):
            continue
        if not cmdline_matches(cmdline, match, comm):
            continue
        found.append(
            ProcInfo(pid=pid, comm=comm, cmdline=cmdline, rank=read_rank(entry))
        )
    found.sort(key=lambda info: info.pid)
    return found
