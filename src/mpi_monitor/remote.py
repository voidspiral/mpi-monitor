"""Build an inline python payload so remote nodes need no package install."""

from __future__ import annotations

import base64
import io
import shlex
import zipfile
from pathlib import Path

_PKG = Path(__file__).resolve().parent


def package_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(_PKG.glob("*.py")):
            zf.write(path, f"mpi_monitor/{path.name}")
    return buf.getvalue()


def remote_boot_source(b64: str) -> str:
    return (
        "import base64,sys,tempfile,zipfile,os\n"
        f"d=base64.b64decode('{b64}')\n"
        "td=tempfile.mkdtemp(prefix='mpi-monitor-')\n"
        "zipfile.ZipFile(__import__('io').BytesIO(d)).extractall(td)\n"
        "sys.path.insert(0, td)\n"
        "from mpi_monitor.cli import main\n"
        "raise SystemExit(main(sys.argv[1:]))\n"
    )


def remote_cmd(argv: list[str] | None = None) -> str:
    b64 = base64.b64encode(package_zip_bytes()).decode("ascii")
    boot = remote_boot_source(b64)
    inner = base64.b64encode(boot.encode("utf-8")).decode("ascii")
    args = " ".join(shlex.quote(a) for a in (argv or []))
    cmd = f"echo {inner} | base64 -d | python3 - {args}".rstrip()
    return cmd
