## Context

See `proposal.md` for motivation. This repo is empty aside from OpenSpec
scaffolding. Neighbor trees ClusterHelm (`scripts/monitor/memmon.py` inline
`--remote-cmd`) and nodestat (host snapshots, ~20s, no PID) are references
only; this change does not edit them.

Constraints: Python 3.10+; stdlib for collect/wrap; matplotlib optional;
compute nodes may have no package install; no hardcoded home paths; TDD with
`unittest` (failing tests first, then implementation).

## Goals / Non-Goals

**Goals:**

- Package a job-scoped sidecar CLI: `wrap` is the happy path; `collect` and
  `plot` exist for tests and attach-style debugging.
- Keep remote sampling deploy-free via an inline SSH payload.
- Make collector lifetime bound to the wrapped command and matching PIDs.

**Non-Goals:**

- ClusterHelm workflow/skill wiring, nodestat schema changes, daemons, PMPI,
  Grafana, or interactive HTML (see proposal Non-goals).
- Multi-pid overlay charts or a long-running HTTP service.

## Decisions

### 1. Job-lifecycle sidecar, not a node daemon or PMPI

Wrap starts per-host collectors, runs the user command, then stops collectors.
Ranks are discovered from `/proc` cmdline + optional rank env, not by linking
the user binary.

**Alternatives:** node daemon (always-on, must filter jobs, extra ops); PMPI
(requires rebuild). Rejected for v1.

### 2. Python package layout and CLI surface

```
src/mpi_monitor/     # library: /proc parse, discover, collect, plot, wrap
tests/               # unittest, no network in unit tests
pyproject.toml       # script mpi-monitor
```

CLI:

- `mpi-monitor wrap --hosts h1,h2 --match BIN --output-dir DIR [--interval SEC] -- CMD...`
- `mpi-monitor collect --match ... --output-dir ... --stop-file ...` (node-local)
- `mpi-monitor plot --run-dir DIR`
- `mpi-monitor remote-cmd` prints the inline collector one-liner (tests + SSH)

Hosts, SSH user/identity, output dir, interval, ready-timeout, and match come
from flags (and later a config file). Never `/home/<user>/...` literals.

**Alternatives:** single script in `scripts/` (harder to test as a library);
tying CLI to ClusterHelm `mem-api.sh` patterns. Rejected: this is its own repo.

### 3. Implementation method: TDD

Write failing `unittest` cases first: `/proc` parse fixtures, match/exclude,
JSONL schema, PNG names, wrap lifecycle with a short local process (`sleep` /
CPU burner), remote-cmd payload round-trip without live SSH (mock or
`--remote-cmd` encoding). Then implement until tests pass. Integration tests
that SSH to a cluster are optional and gated.

### 4. Metrics from `/proc`, interval configurable

| Field | Source |
|-------|--------|
| `cpu_pct` | `/proc/<pid>/stat` utime+stime deltas vs wall time (CLK_TCK) |
| `rss_mb` | `/proc/<pid>/status` VmRSS |
| `io_*_bps` | `/proc/<pid>/io` `read_bytes` / `write_bytes` deltas |

Default `--interval` is `1.0` seconds. Short jobs (NPB class S) pass a smaller
interval (e.g. `0.1`). Ready timeout (default 30s) waits for the first match
after MPI spawn.

**Alternatives:** `pidstat` (interval floor, extra package); host `/proc/stat`
(violates process-level spec).

### 5. Remote collect: inline payload over SSH, local host in-process

Same idea as ClusterHelm `memmon.py --remote-cmd`: base64-encode the collector
module and run `python3` on the remote stdin. Local hostname (short name) runs
`collect` in a subprocess, no SSH.

Stop signal: a stop file path under the run dir. Local: filesystem. Remote:
SSH `touch` the remote stop file (under `/tmp/mpi-monitor/<run_id>/`) then
`scp` JSONL back. Join timeout after wrap returns so SSH cannot hang the CLI.

**Alternatives:** require package install on every node (fails today's
cn2-without-files pattern); gateway polling `/proc` over SSH every interval
(latency, load).

### 6. Run directory layout

```
{output_dir}/{run_id}/
  meta.json          # hosts, match, command, interval, start/end
  series/{host}_pid{pid}.jsonl
  charts/{run_id}_{host}_pid{pid}_{cpu|rss|io_read|io_write}.png
```

`run_id` defaults to UTC timestamp + pid of wrap. Plot is best-effort:
missing matplotlib warns and skips PNGs; wrap exit status stays the job's.

### 7. Exclude list and rank keys

Exclude comm/exe basename set: `mpirun`, `mpiexec`, `orted`, `orterun`,
`prted`, `prterun`, `sshd`, `hydra_pmi_proxy`, plus the collector's own pid.
Rank env order: `PMIX_RANK`, `OMPI_COMM_WORLD_RANK`, `PMI_RANK`.

## Risks / Trade-offs

- [Short jobs with default 1s interval yield 0–1 samples] → document
  `--interval`; tests cover sub-second wrap with a small interval.
- [MPI ranks appear after mpirun] → ready timeout; empty series is allowed
  and reported, not a hang.
- [SSH hang / missing python3 on a node] → per-host timeout, continue other
  hosts, non-zero wrap only if the user command failed (collect errors in
  `meta.json` and stderr).
- [cpu_pct can exceed 100 on multi-thread ranks] → record as computed; no
  clamp in v1.
- [Optional matplotlib] → tests that assert PNG names skip or mock the
  backend when the extra is absent; a dedicated test uses a stub plotter.

## Migration Plan

- New repo: no production migration. Tag v0.1 after tests pass.
- Operators copy or `pip install` on the launch host only.
- Rollback: stop using the CLI; collectors are not daemons.
- Later ClusterHelm integration (out of scope) would wrap this same CLI.

## Open Questions

- Config file format (`toml` vs flags-only) can wait; flags are enough for v1.
- Whether wrap should default `--hosts` to `localhost` if unspecified would
  change the spec (currently fail-closed); leave fail-closed.
