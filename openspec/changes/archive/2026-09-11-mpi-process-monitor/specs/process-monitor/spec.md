## Purpose

Provides a standalone CLI that wraps an HPC job command, finds matching task
processes on named compute hosts, and records process-level CPU, memory, and IO
timeseries until those processes and the wrapped command have finished.

## ADDED Requirements

### Requirement: Wrap command is the primary invocation
The CLI SHALL provide a wrap invocation that starts collectors on the listed
hosts, runs a caller-supplied command, stops collectors when that command
returns, and exits with the wrapped command's exit status.

#### Scenario: Successful wrap of a short local command
- **WHEN** the user wraps a finite command with at least one matching process on a listed host
- **THEN** the CLI runs the command to completion, writes JSONL samples for the matching process, stops collectors, and returns the command's exit code

#### Scenario: Wrapped command failure is preserved
- **WHEN** the wrapped command exits non-zero
- **THEN** the CLI still stops collectors and writes any samples collected, and the CLI exit code SHALL equal the wrapped command's exit code

### Requirement: Sampling is process-level on named hosts
The monitor SHALL sample matching task processes (host + pid, optional MPI
rank), not whole-node averages. Hosts SHALL come from CLI flags or a config
file; the implementation MUST NOT hardcode user home directories or hostnames.

#### Scenario: Two-host MPI-style match
- **WHEN** wrap is given two hosts and a match string that identifies the rank binary
- **THEN** samples include both hosts' matching pids when those processes ran, each sample carrying `host` and `pid`

#### Scenario: Host list is explicit
- **WHEN** the user omits hosts and no config file supplies them
- **THEN** the CLI SHALL fail with a non-zero exit and an error on stderr instead of inventing a host list

### Requirement: Process discovery matches cmdline and excludes helpers
On each host the collector SHALL select processes whose **executable** (comm
or argv0) contains the caller-supplied match string, and MUST exclude MPI
launchers, daemons, sshd, the SSH client used to start collectors, and the
collector process itself. A match that appears only in later argv (for example
`wrap --match is.S.x` or `mpirun ... is.S.x`) MUST NOT select that process.

#### Scenario: Rank binary is selected
- **WHEN** a host has `is.S.x` and `mpirun` processes
- **THEN** only the `is.S.x` pid is sampled when match is `is.S.x`

#### Scenario: Launcher processes are excluded
- **WHEN** cmdline contains `mpirun`, `mpiexec`, `orted`, `orterun`, `prted`, `prterun`, `sshd`, `ssh`, or `hydra_pmi_proxy`
- **THEN** that pid MUST NOT be sampled even if the match string also appears

#### Scenario: Wrap and collect argv are not sampled
- **WHEN** a python wrap/collect process or an `ssh` helper has `--match is.S.x` in later argv, and a rank binary `is.S.x` is also running
- **THEN** only the rank binary pid is sampled

### Requirement: Optional MPI rank from process environment
When a matched process exposes a known rank environment variable, each sample
SHALL include that rank. When none is present, rank MAY be omitted and the
sample MUST still include host and pid.

#### Scenario: Rank from PMIx or PMI
- **WHEN** the process environment contains `PMIX_RANK`, `OMPI_COMM_WORLD_RANK`, or `PMI_RANK`
- **THEN** samples for that pid include the corresponding integer `rank`

#### Scenario: No rank environment
- **WHEN** none of those variables are set
- **THEN** samples still record `host` and `pid` without failing

### Requirement: JSONL timeseries schema
Each sample line SHALL be a JSON object with at least: `ts` (Unix epoch
seconds, float), `host`, `pid`, `cpu_pct`, `rss_mb`, `io_read_bps`,
`io_write_bps`. Files SHALL be written under the run directory as
`series/{host}_pid{pid}.jsonl`.

#### Scenario: Schema keys present
- **WHEN** at least one sample is written
- **THEN** every JSONL object contains the required keys and `cpu_pct`, `rss_mb`, `io_read_bps`, and `io_write_bps` are numbers

#### Scenario: One file per process
- **WHEN** two pids are sampled
- **THEN** the run directory contains two series files named with host and pid

### Requirement: Collectors follow job lifetime
Collectors SHALL start before the wrapped command, wait up to a configurable
ready timeout for matching pids, sample at a configurable interval, take a
small number of trailing samples after matching pids disappear, then exit.
Collectors MUST stop when the wrap command returns even if pids remain.
Collectors MUST NOT loop indefinitely after the job ends.

#### Scenario: Short job stops the monitor
- **WHEN** matching pids exit and the wrapped command has returned
- **THEN** collectors exit after at most two additional sample intervals

#### Scenario: Wrap return stops collectors
- **WHEN** the wrapped command returns while a collector is still running
- **THEN** wrap signals collectors to stop and does not wait beyond a bounded join timeout

### Requirement: Remote hosts without a prior install
For a host that is not the local machine, the launch host SHALL start the
collector over SSH using an inline payload so the remote node needs `python3`
and `/proc`, not a pre-installed copy of this package.

#### Scenario: Remote inline collect
- **WHEN** wrap lists a remote host that has python3 but not this package
- **THEN** sampling still produces JSONL for matching pids on that host, or wrap reports a per-host collect error without hanging

#### Scenario: Local host skips SSH
- **WHEN** a listed host is the local hostname
- **THEN** the collector runs locally without SSH
