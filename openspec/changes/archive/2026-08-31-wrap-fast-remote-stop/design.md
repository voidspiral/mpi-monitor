## Context

See proposal.md for why wrap wall time currently tracks serial SSH and a
remote pid-wait loop. Implementation lives in `src/mpi_monitor/wrap.py`:
`default_ssh_run`, `_start_remote_collector`, `_remote_finalize_command`,
`_finalize_remote_series`, and the host loop inside `wrap`. Collectors still
start before the wrapped command; this design only changes how SSH is budgeted
and overlapped.

Constraints: Python 3.10+ stdlib; no new CLI flags; TDD with `unittest`.

## Goals / Non-Goals

**Goals:**

- Parallel remote start and finalize so N hosts cost one SSH RTT, not N.
- Fixed `ConnectTimeout=10`; outer `subprocess.run` timeout at least connect + 2
  (finalize uses `max(join_timeout, connect + 5)`).
- One SSH finalize transaction: `touch stop; kill; tar | base64`.
- Keep wrap exit code = application exit; fetch errors stay partial.

**Non-Goals:**

- Overlapping the user command with collector start.
- New flags or changes to `collect_loop`.
- Killing leftover collectors from older runs (out of band).

## Decisions

### 1. ThreadPoolExecutor for host SSH

Use `concurrent.futures.ThreadPoolExecutor` over remote hosts for start and
again for finalize. Local hosts stay on the calling thread via `spawn_local`.
Per-host exceptions are recorded in `collect_errors` like today.

**Alternatives:** `asyncio` (no async SSH wrapper in stdlib); `multiprocessing`
(heavier, harder to share `ssh_run` mocks).

### 2. Connect timeout is constant 10s

Today `ConnectTimeout = max(1, int(timeout - 2))`, so `--join-timeout 5`
becomes connect=3 and the outer timeout is 5s. On this cluster SSH often
takes 3–19s, so finalize never runs `touch`.

`default_ssh_run` always passes `ConnectTimeout=10`. If the caller’s
`timeout` is smaller, raise the outer timeout to `max(timeout, 12)` so
OpenSSH is not killed before connect expires. Finalize passes
`max(join_timeout, 15)` so connect (10) plus `touch`/`kill`/`tar` fit.

**Alternatives:** a `--ssh-timeout` flag (rejected; no new CLI); keep shrinking
connect from join-timeout (fails on this cluster).

### 3. Kill instead of pid wait loop

`_remote_finalize_command` becomes: `touch stop`; read pid file; `kill`
(TERM, ignore failure); tar series. JSONL is line-appended, so a kill mid-loop
leaves a complete last line or omits the in-flight sample.

Keep one retry inside `_finalize_remote_series` (same as today) so a single
transient SSH still gets a second chance; parallel hosts mean wall time is
`max(attempt)`, not the sum across hosts.

**Alternatives:** two SSH calls (stop, then fetch) — extra RTT; wait loop with
a longer timeout — still races join-timeout.

### 4. Implementation method is TDD

Write failing unittest cases first (parallel wall clock, connect timeout,
finalize command shape), then implement until `python3 -m unittest discover
-s tests` passes.

**Alternatives:** implement then test (rejected by project rules).

## Risks / Trade-offs

- [Kill before tar races a last sample] → Accept; line-oriented JSONL; trailing
  samples remain a collect-loop concern for local/clean stop.
- [ThreadPool plus mock ssh_run is not thread-safe] → Tests use a lock or
  append-only list; production `subprocess.run` is per-thread.
- [15s finalize timeout still too short if SSH is 19s] → Start still uses
  `ready_timeout` (30s). Finalize 15s covers typical 3–12s connects; remaining
  timeouts stay partial, not a 60s serial pile-up.
- [Orphan collectors if kill pid is the setsid parent] → TERM the pid recorded
  at start (`$!` of `setsid bash -c`); that process group should exit.

## Migration Plan

No CLI migration. Deploy the package / inline payload together (payload is
zipped from the same tree). Rollback: previous wrap; leftover `/tmp/mpi-monitor`
dirs are harmless once collectors exit via ready-timeout.

## Open Questions

None.
