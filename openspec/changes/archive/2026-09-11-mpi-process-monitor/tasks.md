## 1. Package skeleton

- [x] 1.1 Add `pyproject.toml` (Python ≥3.10, optional `plot` extra for matplotlib, console script `mpi-monitor`) and an empty `src/mpi_monitor` package; verify `python3 -c "import tomllib, pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text())"` succeeds and the script entry is declared
- [x] 1.2 Add `.gitignore` for `__pycache__`, `*.egg-info`, `.venv`, and run output dirs; verify `git check-ignore -v src/mpi_monitor.egg-info` would match after a local build

## 2. /proc parse and discovery (tests first)

- [x] 2.1 Write failing unittest fixtures for `/proc/<pid>/stat`, `status` (VmRSS), and `io` parsing (cpu_pct from utime+stime deltas, rss_mb, io rates); verify `python3 -m unittest tests.test_proc_parse` fails with import/attribute errors
- [x] 2.2 Implement `/proc` parsers to match the fixtures; verify `python3 -m unittest tests.test_proc_parse` passes
- [x] 2.3 Write failing tests that cmdline match selects the rank binary and excludes `mpirun`/`mpiexec`/`orted`/`orterun`/`prted`/`prterun`/`sshd`/`hydra_pmi_proxy` plus the collector pid; verify `python3 -m unittest tests.test_discover` fails
- [x] 2.4 Implement discovery; verify `python3 -m unittest tests.test_discover` passes
- [x] 2.5 Write failing tests that rank is read from `PMIX_RANK` / `OMPI_COMM_WORLD_RANK` / `PMI_RANK` and omitted when absent; verify they fail then implement until `python3 -m unittest tests.test_rank` passes

## 3. JSONL collect loop (tests first)

- [x] 3.1 Write failing tests for JSONL schema keys (`ts`, `host`, `pid`, `cpu_pct`, `rss_mb`, `io_read_bps`, `io_write_bps`) and `series/{host}_pid{pid}.jsonl` naming using a fake sampler; verify `python3 -m unittest tests.test_jsonl` fails
- [x] 3.2 Implement collect-to-JSONL; verify `python3 -m unittest tests.test_jsonl` passes
- [x] 3.3 Write failing tests that collect exits after matching pids disappear (≤2 extra intervals) and when a stop file appears; verify they fail then implement until `python3 -m unittest tests.test_collect_lifecycle` passes

## 4. Charts (tests first)

- [x] 4.1 Write failing tests for PNG names `{run_id}_{host}_pid{pid}_{cpu|rss|io_read|io_write}.png`, one file per process×metric, and skip on empty series; verify `python3 -m unittest tests.test_plot_names` fails
- [x] 4.2 Implement filename helpers (and a stub/matplotlib plotter); verify `python3 -m unittest tests.test_plot_names` passes
- [x] 4.3 Write a failing test that missing matplotlib warns, leaves JSONL, and does not raise; verify it fails then implement until `python3 -m unittest tests.test_plot_optional` passes

## 5. CLI wrap and remote-cmd (tests first)

- [x] 5.1 Write failing tests that wrap without `--hosts` exits non-zero, local wrap of a short matching process writes series and preserves the command exit code, and `remote-cmd` stdout is a decodable python payload; verify `python3 -m unittest tests.test_cli` fails
- [x] 5.2 Implement CLI (`wrap`, `collect`, `plot`, `remote-cmd`) with flags only (no hardcoded home paths); verify `python3 -m unittest tests.test_cli` passes
- [x] 5.3 Write failing tests that wrap treats the local hostname as in-process (no SSH) and remote hosts use SSH helpers with a mock; verify they fail then implement until `python3 -m unittest tests.test_wrap_hosts` passes
- [x] 5.4 Write failing tests that wrap join is bounded after the command returns (stop file + timeout, no infinite wait); verify they fail then implement until `python3 -m unittest tests.test_wrap_stop` passes

## 6. README and full suite

- [x] 6.1 Add README with wrap example, `--interval` for short jobs, output layout, and matplotlib extra; verify it documents `--hosts` as required
- [x] 6.2 Run `python3 -m unittest discover -s tests` and confirm all tests pass with no `/home/smt` or `/home/cn1` literals in `src/`
