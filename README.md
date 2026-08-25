# mpi-monitor

[中文说明](README.zh.md)

Standalone HPC sidecar that samples **task processes** (MPI ranks or any matched
binary) for CPU, RSS, and IO, then writes JSONL timeseries and optional PNG
charts. It is not ClusterHelm and not nodestat.

Collectors follow the wrapped command: they start first, stop when the command
returns (and after matching PIDs disappear). Compute nodes do not need a prior
install; remote hosts get an inline Python payload over SSH.

## Install

```bash
pip install -e .
# optional PNG extra
pip install -e ".[plot]"
```

Requires Python 3.10+. Plotting uses matplotlib when the `plot` extra is
installed; without it, JSONL is still written.

## Wrap a job

`--hosts` is **required**. Do not omit it.

```bash
mpi-monitor wrap \
  --hosts cn1,cn2 \
  --match is.S.x \
  --output-dir ./runs \
  --interval 0.1 \
  -- \
  mpirun -np 2 -ppn 1 -hosts cn1,cn2 /home/NPB3.4.3/NPB3.4-MPI/bin/is.S.x
```

- `--match` is a substring of `/proc/<pid>/cmdline` (the rank binary, not `mpirun`).
- Default `--interval` is `1.0` seconds. Short jobs (NPB class S, sub-second)
  should pass a smaller value such as `--interval 0.1`.
- Exit status is the wrapped command's exit status.

Local hostname (and `localhost`) runs the collector in-process; other names
are reached with SSH (`--ssh-user`, `--ssh-identity` if needed).

## Output layout

```
{output-dir}/{run_id}/
  meta.json
  series/{host}_pid{pid}.jsonl
  charts/{run_id}_{host}_pid{pid}_{cpu|rss|io_read|io_write}.png
```

Each JSONL line includes `ts`, `host`, `pid`, `cpu_pct`, `rss_mb`,
`io_read_bps`, `io_write_bps`, and `rank` when PMI/PMIx/Open MPI expose it.

## Other commands

```bash
mpi-monitor collect --match BIN --output-dir DIR --stop-file FILE --host HOST
mpi-monitor plot --run-dir DIR
mpi-monitor remote-cmd -- collect --match BIN --output-dir DIR --stop-file FILE --host HOST
```

`remote-cmd` prints a `base64 | python3` one-liner for nodes that do not have
this package installed.

## Tests

```bash
python3 -m unittest discover -s tests
```
