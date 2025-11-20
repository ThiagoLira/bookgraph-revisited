Pipeline profiling
==================

Experiments around the citation pipeline (full runs and stage-specific).

- `mock_run.sh`: quick pipeline smoke test; produces `mock_profile.prof`.
- `pipeline_profile.prof`: profile capture from a pipeline run.
- `stage3_experiment/`: standalone Goodreads agent stage with canned preprocessed inputs and helpers to launch a local llama.cpp server. See its README for CLI details.

Run from repo root for correct paths, e.g.:
```bash
sh profiling/pipeline/mock_run.sh
uv run python profiling/pipeline/stage3_experiment/run_agent_stage3.py ...
```
