## Why

HPC MPI jobs need process-level CPU, memory, and IO timeseries on the compute
nodes that actually run ranks, then independent PNG charts. Ad-hoc `/proc`
scripts hang after the MPI process exits, miss remote nodes that have no
deployed files, and mix host averages with rank PIDs. This repo exists to
provide that monitor as a standalone, deterministic CLI.

## What Changes

- Add a Python CLI that wraps a user command (typically `mpirun`), discovers
  matching task processes on named hosts, samples CPU / RSS / IO until those
  processes exit, and writes JSONL timeseries plus PNG charts.
- Sample at process granularity (host + pid, optional MPI rank), not whole-node
  averages. Exclude launcher/runtime helpers (`mpirun`, `orted`, `sshd`, the
  collector itself).
- Reach compute nodes that do not have this package installed by sending an
  inline collector payload over SSH.
- Stop collectors when the wrapped command returns and when matching PIDs are
  gone (a few trailing samples, then exit). No unbounded monitor loops.

## Non-goals

- Not a ClusterHelm slave workflow, OpenCode skill, or `workflow_runner` hook.
  ClusterHelm may call this CLI later; that integration is out of scope.
- Not an extension of nodestat (host heartbeat snapshots, no PID/rank).
- No Prometheus/Grafana, no interactive HTML, no in-process PMPI instrumentation,
  no node-resident daemon.
- No hardcoded user home paths. Hosts, output directory, and SSH options come
  from CLI flags or config files.

## Capabilities

### New Capabilities

- `process-monitor`: wrap a command, discover task PIDs, sample CPU/mem/IO,
  write JSONL, and stop with the job.
- `timeseries-charts`: emit independently named PNG curves (one file per
  process × metric) from JSONL, with matplotlib optional.

### Modified Capabilities

- (none; this repository has no baseline specs yet)

## Impact

- **New package:** Python 3.10+ library and `mpi-monitor` CLI under this repo.
- **Outputs:** per-run directory with `series/*.jsonl` and `charts/*.png`.
- **Dependencies:** stdlib for collect/wrap; matplotlib optional for plots.
- **Operations:** SSH from the launch host to `--hosts`; inline remote payload
  so compute nodes need `python3` and `/proc`, not a prior install.
- **Neighbors:** ClusterHelm and nodestat are reference-only; this change does
  not edit those trees.
