## Why

On this cluster, wrapping a 0.3s NPB class-S job can take ~60s of wrap wall
time. The extra time is serial SSH start/finalize plus a remote pid-wait loop
that equals `--join-timeout`, so stop files often never land and ClusterHelm
attributes the hang to a "collection window". Collectors must follow the
wrapped command, not SSH retry arithmetic.

## What Changes

- Start and finalize remote collectors **in parallel** across `--hosts`
  (local spawn stays in-process).
- Keep SSH `ConnectTimeout` independent of `--join-timeout` (fixed 10s), and
  raise the SSH outer timeout so connect plus `touch`/`kill`/`tar` can finish.
- Finalize with `touch stop; kill; tar` in one SSH transaction. Do **not**
  wait up to 5s inside the remote shell for the collector pid.
- Keep wrap exit status equal to the wrapped command. Slow or failed fetch
  stays `collection_status=partial` with `ended_at` always written.

## Non-goals

- Do not overlap `mpirun` with collector start (collectors still start first).
- No new CLI flags (`--ssh-timeout` or similar).
- No change to `collect_loop` ready/trailing semantics.
- No ClusterHelm profiler or job-JSON changes.

## Capabilities

### New Capabilities

- (none)

### Modified Capabilities

- `process-monitor`: remote collector start/stop MUST be concurrent; SSH
  connect budget MUST NOT be derived by shrinking join-timeout; wrap MUST
  deliver a remote stop (touch + kill) instead of a wait loop whose duration
  equals the SSH timeout; wall time after the command returns MUST track one
  SSH RTT plus join, not `N × (join-timeout + retry)`.

## Impact

- **Code:** `src/mpi_monitor/wrap.py` start/finalize and `default_ssh_run`.
- **Tests:** `tests/test_wrap_hosts.py` (and wrap-stop if timeouts change).
- **Docs:** `docs/known-issues.md`.
- **CLI:** existing flags only; `--join-timeout` and `--ready-timeout` keep
  their names and defaults.
- **Dependencies:** stdlib `concurrent.futures` only.
