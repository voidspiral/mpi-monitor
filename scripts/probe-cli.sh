#!/usr/bin/env bash
# CLI hard gate for mpi-monitor. Invoke via array expansion, never:
#   MPI_MON="python3 -m mpi_monitor"; "$MPI_MON"
# which treats the whole string as a pathname ("No such file").
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="${MPI_MONITOR_VENDOR:-$ROOT}"
VENV_BIN="${VENDOR}/.venv/bin/mpi-monitor"
SRC="${VENDOR}/src"

argv=()
if command -v mpi-monitor >/dev/null 2>&1; then
  argv=("$(command -v mpi-monitor)")
elif [[ -x "$VENV_BIN" ]]; then
  argv=("$VENV_BIN")
elif PYTHONPATH="${SRC}${PYTHONPATH:+:$PYTHONPATH}" python3 -c "import mpi_monitor" >/dev/null 2>&1; then
  argv=(env "PYTHONPATH=${SRC}${PYTHONPATH:+:$PYTHONPATH}" python3 -m mpi_monitor)
elif python3 -c "import mpi_monitor" >/dev/null 2>&1; then
  argv=(python3 -m mpi_monitor)
else
  echo "mpi-monitor CLI is not installed on this gateway" >&2
  exit 2
fi

"${argv[@]}" probe >/dev/null
echo "HARD_GATE: OK -> ${argv[*]}"
python3 -c 'import json,sys; print(json.dumps({"argv": sys.argv[1:]}))' "${argv[@]}"
