## ADDED Requirements

### Requirement: Remote collector start and stop are concurrent
When wrap lists more than one remote host, collector start SSH and
post-command finalize SSH SHALL run concurrently across those hosts. A
failure on one host MUST NOT block start or finalize on the others. Wrap
wall time after the wrapped command returns MUST be bounded by one SSH round
trip plus the join timeout, not by the sum of per-host timeouts and retries.

#### Scenario: Two remote hosts start and finalize together
- **WHEN** wrap lists two remote hosts and each SSH helper takes a similar
  non-trivial time
- **THEN** wrap completes in about one of those SSH durations, not the sum,
  and both hosts receive a start and a finalize

#### Scenario: One remote finalize failure is isolated
- **WHEN** finalize fails on one remote host and succeeds on another
- **THEN** wrap still returns the wrapped command's exit code, records a
  per-host collect error, and writes `ended_at` on the run meta

### Requirement: Remote stop is delivered without a pid wait loop
After the wrapped command returns, wrap MUST signal each remote collector by
creating its stop file and sending it a termination signal in the same SSH
transaction that fetches JSONL. Wrap MUST NOT keep that SSH session open by
polling whether the collector pid is still alive for a duration that equals
the SSH timeout.

#### Scenario: Finalize touches stop, kills, and fetches in one session
- **WHEN** wrap finalizes a remote collector
- **THEN** the remote command creates the stop file, signals the collector
  process, and returns a tar archive of any series files, without a sleep
  loop waiting on the collector pid

#### Scenario: Slow SSH still delivers stop
- **WHEN** SSH connect needs several seconds but stays under the connect
  timeout
- **THEN** the remote stop file is created and wrap does not treat a
  successful connect as a timeout solely because join-timeout was used as
  the SSH connect budget

### Requirement: SSH connect timeout is independent of join-timeout
SSH connect timeout SHALL be a fixed connect budget, not derived by
subtracting from `--join-timeout`. The SSH process timeout MUST be at least
the connect timeout plus time to run the remote command.

#### Scenario: Short join-timeout does not shrink connect timeout
- **WHEN** wrap is invoked with the default join timeout (5 seconds)
- **THEN** SSH still uses a 10 second connect timeout, and the outer SSH
  timeout is greater than or equal to that connect timeout
