# mpi-monitor

独立的 HPC 作业伴生监控：按**任务进程**（MPI rank 或任意匹配到的二进制）采集 CPU、RSS、IO，写出 JSONL 时序，并可选生成 PNG 曲线。本仓库不是 ClusterHelm，也不是 nodestat。

[English README](README.md)

采集器跟着被包装的命令走：先启动、命令返回后停止（匹配 PID 消失后再采少量尾点）。计算节点不必预装本包；远程主机通过 SSH 下发内联 Python payload。

**单机多进程可以监控。** `--hosts` 填本机短主机名或 `localhost` 时，采集器在本地跑，不走 SSH。

## 安装

```bash
pip install -e .
# 可选：出 PNG（需要 matplotlib）
pip install -e ".[plot]"
```

需要 Python 3.10+。无 matplotlib 时仍会写 JSONL，只是跳过 PNG。Debian/Ubuntu 也可：

```bash
sudo apt install python3-matplotlib
PYTHONPATH=src python3 -m mpi_monitor wrap ...
```

## 包装作业（wrap）

`--hosts` **必填**，不能省略。

多机：

```bash
mpi-monitor wrap \
  --hosts cn1,cn2 \
  --match is.S.x \
  --output-dir ./runs \
  --interval 0.1 \
  -- \
  mpirun -np 2 -ppn 1 -hosts cn1,cn2 /home/NPB3.4.3/NPB3.4-MPI/bin/is.S.x
```

单机多进程（本机 4 个 rank）：

```bash
mpi-monitor wrap \
  --hosts "$(hostname -s)" \
  --match ep.C.x \
  --output-dir ./runs \
  --interval 0.1 \
  -- \
  mpirun --oversubscribe -np 4 /path/to/ep.C.x
```

- `--match` 是 `/proc/<pid>/cmdline` 的子串，应指向 **rank 二进制**（如 `ep.C.x`），不要匹配 `mpirun`。
- 默认 `--interval` 为 `1.0` 秒。短作业（NPB class S、亚秒级）请改小，例如 `0.1` 或 `0.05`。
- wrap 的退出码等于被包装命令的退出码。
- 本机短主机名和 `localhost` 走本地采集；其它主机名走 SSH（可用 `--ssh-user`、`--ssh-identity`）。

## 输出目录

```
{output-dir}/{run_id}/
  meta.json
  series/{host}_pid{pid}.jsonl
  charts/{run_id}_{host}_pid{pid}_{cpu|rss|io_read|io_write}.png
```

JSONL 每行至少包含：`ts`、`host`、`pid`、`cpu_pct`、`rss_mb`、`io_read_bps`、`io_write_bps`。若进程环境里有 `PMIX_RANK` / `OMPI_COMM_WORLD_RANK` / `PMI_RANK`，还会带 `rank`。

每个进程、每项指标一张独立 PNG，不把多个 PID 叠在同一张图上。

## 其它命令

```bash
mpi-monitor collect --match BIN --output-dir DIR --stop-file FILE --host HOST
mpi-monitor plot --run-dir DIR
mpi-monitor remote-cmd -- collect --match BIN --output-dir DIR --stop-file FILE --host HOST
mpi-monitor probe
mpi-monitor job-json          # {AGENT_JOB_DIR}/{AGENT_JOB_ID}.json（不是再套一层目录）
bash scripts/probe-cli.sh     # 硬门禁；用 argv 数组，不要 "$MPI_MON"
```

`remote-cmd` 打印一条 `base64 | python3` 命令，给未安装本包的计算节点用。

## 测试

```bash
python3 -m unittest discover -s tests
```
