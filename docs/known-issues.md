# Known issues

Recorded 2026-08-26 from ClusterHelm test partition and cn[1-3] wrap of NPB /
`mpi_loop.x`. Hard-gate / job-JSON mistakes seen in gateway agent logs
2026-08-28.

## CLI hard gate / job JSON — fixed

Reproduced on cn1 agent logs (`job-20260828T001848Z-1931`, `…4144`):

1. `"$MPI_MON"` when `MPI_MON="env PYTHONPATH=… python3 -m mpi_monitor"` →
   `No such file or directory`. Fix: `scripts/probe-cli.sh` (bash array) or
   `python3 -m mpi_monitor probe`.
2. Ad-hoc `finalize.py` opened
   `{AGENT_JOB_DIR}/{job_id}/{job_id}.json` (extra directory) →
   `FileNotFoundError`. Real file is `{AGENT_JOB_DIR}/{job_id}.json`.
   Print it with `python3 -m mpi_monitor job-json`.

## wrap SSH sidecar timeout — fixed

Remote start now detaches:

```text
mkdir -p ... && (setsid bash -c '<payload>' >/dev/null 2>collect.err </dev/null &) && echo OK
```

The job must be backgrounded **inside a subshell**. `nohup ... & echo OK`
still holds the SSH session on this cluster (repro: `ssh cn2 'nohup sleep 8
... &'` hangs until sleep ends). `(sleep 8 ... &); echo OK` returns in ~1s
and the process survives. SSH start also uses `-T -n`.

Previously `nohup` only covered `echo`, so SSH waited until `python3 collect`
exited (`ready_timeout`). A timed-out local `ssh` can leave orphan collectors
on the remote node; they keep scanning `/proc` until killed.

## `--match` self-matches — fixed

`discover()` matches **comm or argv0** only, not later argv. Wrap/collect
`--match is.S.x` and `mpirun ... is.S.x` are no longer sampled. `ssh` is in
the launcher exclude list.

## wrap serial SSH + join-timeout connect budget — fixed

Reproduced on cn1 wrapping `is.S.x` (NPB kernel 0.3–0.6s): three-host wrap
wall clock **~59s**. Start/finalize ran host-by-host. Finalize used
`--join-timeout` (default 5s) as the SSH outer timeout and set
`ConnectTimeout=join_timeout-2` (3s). cn2/cn3 SSH often takes 3–19s, so
`touch stop` never ran; wrap then retried 10s per host (**30s** of timeouts).

Now:

- Remote start and finalize run **concurrently** (`ThreadPoolExecutor`).
- SSH `ConnectTimeout` is always **10s**. Outer timeout is at least
  `connect + 2` (finalize uses `max(join_timeout, 15)`).
- Finalize is `touch stop; kill $pid; tar | base64` — no `while kill -0; sleep
  0.1` loop that ate the whole 5s SSH budget.

`--join-timeout` still bounds local collector join. Slow fetch stays
`collection_status=partial`.

## `ready_timeout` is also the SSH start timeout

Still the same CLI flag for the start SSH outer timeout. ConnectTimeout is no
longer derived from it. After the detach fix, start should return after one
SSH RTT. If SSH itself is slow (WSL proxy), raise `--ready-timeout`.
