## Purpose

Turns process-monitor JSONL timeseries into independently named PNG charts, one
file per sampled process and metric, so operators can inspect CPU, memory, and
IO curves after an HPC job without embedding binaries in reports.

## ADDED Requirements

### Requirement: One PNG per process and metric
From a run's JSONL series, the plot step SHALL write one PNG per sampled
process for each of `cpu`, `rss`, `io_read`, and `io_write`. Filenames SHALL
follow `{run_id}_{host}_pid{pid}_{metric}.png` under `charts/` in the run
directory.

#### Scenario: Four charts for one process
- **WHEN** a run directory contains JSONL for one host and pid and plotting succeeds
- **THEN** `charts/` contains exactly four PNGs named with that run id, host, pid, and the four metric suffixes

#### Scenario: Two processes produce separate files
- **WHEN** JSONL exists for two pids
- **THEN** each pid has its own four PNG files; charts MUST NOT overlay multiple pids on one image

### Requirement: Charts are time series of the sampled metric
Each PNG SHALL plot sample time on the x-axis and the corresponding metric on
the y-axis (`cpu_pct`, `rss_mb`, `io_read_bps`, `io_write_bps`).

#### Scenario: Empty series skips that process
- **WHEN** a series file exists but contains no valid samples
- **THEN** the plot step MUST NOT emit charts for that pid and MUST report the skip

### Requirement: Plotting is optional when matplotlib is missing
If matplotlib is not importable, the plot step SHALL leave JSONL in place,
emit a warning on stderr, skip PNG creation, and MUST NOT fail the wrap solely
because plots could not be drawn.

#### Scenario: JSONL retained without matplotlib
- **WHEN** wrap completes sampling but matplotlib cannot be imported
- **THEN** series JSONL remains on disk, no PNG is required, and wrap still returns the wrapped command's exit code
