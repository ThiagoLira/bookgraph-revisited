GPU profiling
=============

Harnesses for stressing llama.cpp locally and capturing GPU utilization.

- `single_gpu/`: launches llama-server on one GPU and runs `run_single_file.py` with monitoring. See the script for tunables.
- `dual_gpu/`: sweeps concurrency with row-split tensor parallelism across two GPUs.
- `common/`: shared helpers (e.g., `monitor_gpu_util.sh`).

Run from repo root, e.g.:
```bash
profiling/gpu/single_gpu/run_profiled_single.sh
profiling/gpu/dual_gpu/run_profiled_dual.sh
```
