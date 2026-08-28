"""ClusterHelm path helpers and CLI hard-gate argv resolution.

ClusterHelm job files live next to each other under AGENT_JOB_DIR:

    {AGENT_JOB_DIR}/{job_id}.json
    {AGENT_JOB_DIR}/{job_id}.incident.json
    {AGENT_JOB_DIR}/{job_id}.agent.log

Not ``{AGENT_JOB_DIR}/{job_id}/{job_id}.json`` (an extra directory).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path


WhichFn = Callable[[str], str | None]


def job_json_path(
    *,
    job_dir: str | None = None,
    job_id: str | None = None,
    environ: dict[str, str] | None = None,
) -> Path:
    """Return the ClusterHelm job JSON path (flat file, not a nested dir)."""
    env = environ if environ is not None else os.environ
    job_dir = (job_dir if job_dir is not None else env.get("AGENT_JOB_DIR", "")).strip()
    job_id = (job_id if job_id is not None else env.get("AGENT_JOB_ID", "")).strip()
    if not job_dir or not job_id:
        raise ValueError("AGENT_JOB_DIR and AGENT_JOB_ID are required")
    return Path(job_dir) / f"{job_id}.json"


def incident_path_from_env(*, environ: dict[str, str] | None = None) -> Path | None:
    env = environ if environ is not None else os.environ
    raw = env.get("CLUSTERHELM_INCIDENT_PATH", "").strip()
    if raw:
        return Path(raw)
    job_dir = env.get("AGENT_JOB_DIR", "").strip()
    job_id = env.get("AGENT_JOB_ID", "").strip()
    if job_dir and job_id:
        return Path(job_dir) / f"{job_id}.incident.json"
    return None


def resolve_cli_argv(
    *,
    vendor_root: Path | None = None,
    which: WhichFn | None = None,
    venv_bin: Path | None = None,
) -> list[str]:
    """Argv to invoke mpi-monitor. Never a single multi-word string.

    Callers must expand the list (``subprocess`` / bash ``"${argv[@]}"``).
    Quoting the joined string as one pathname raises ``No such file``.
    """
    lookup = which if which is not None else shutil.which
    found = lookup("mpi-monitor")
    if found:
        return [found]
    root = Path(vendor_root) if vendor_root is not None else Path(__file__).resolve().parents[2]
    binary = venv_bin if venv_bin is not None else root / ".venv" / "bin" / "mpi-monitor"
    if binary.is_file() and os.access(binary, os.X_OK):
        return [str(binary)]
    src = root / "src"
    pythonpath = str(src)
    existing = os.environ.get("PYTHONPATH", "").strip()
    if existing:
        pythonpath = pythonpath + os.pathsep + existing
    return ["env", f"PYTHONPATH={pythonpath}", "python3", "-m", "mpi_monitor"]
