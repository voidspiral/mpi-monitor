## 1. Failing tests

- [x] 1.1 Update `test_default_ssh_outer_timeout_exceeds_connect_timeout` so `timeout=5` still uses `ConnectTimeout=10` and the outer `subprocess.run` timeout is ≥ 12; verify `python3 -m unittest tests.test_wrap_hosts.TestWrapHosts.test_default_ssh_outer_timeout_exceeds_connect_timeout` fails
- [x] 1.2 Add a test that the remote finalize command contains `touch` and `kill`, contains `tar`/`base64`, and does not contain `while kill -0` or `sleep 0.1`; verify it fails on the current wait-loop command
- [x] 1.3 Add a test that wrap of two remote hosts with a mock `ssh_run` that sleeps ~0.3s per call finishes in < 0.8s and both hosts get start plus finalize; verify it fails on serial start/finalize
- [x] 1.4 Add a test that finalize timeout on one of two remotes still returns the wrapped exit code, records that host in `collect_errors`, succeeds on the other host, and writes `ended_at`; verify `python3 -m unittest tests.test_wrap_hosts` fails before implementation

## 2. Implementation

- [x] 2.1 Change `default_ssh_run` to a fixed 10s ConnectTimeout and raise the outer timeout to `max(timeout, 12)` when a timeout is passed; verify task 1.1 passes
- [x] 2.2 Replace the remote finalize pid wait loop with `touch stop; kill; tar | base64`, and pass finalize timeout `max(join_timeout, 15)`; verify task 1.2 passes and `test_remote_stop_and_fetch_use_one_transaction` still passes
- [x] 2.3 Parallelize remote start and finalize with `ThreadPoolExecutor`; isolate per-host errors; verify tasks 1.3 and 1.4 pass and `python3 -m unittest tests.test_wrap_hosts tests.test_wrap_stop` passes

## 3. Docs and suite

- [x] 3.1 Record the serial SSH / join-timeout connect-budget issue and the parallel kill-then-tar fix in `docs/known-issues.md`; verify the file names ConnectTimeout=10 and concurrent finalize
- [x] 3.2 Run `python3 -m unittest discover -s tests` and confirm the full suite passes
