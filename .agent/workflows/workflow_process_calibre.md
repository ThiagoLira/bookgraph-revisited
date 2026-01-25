---
description: Process a Calibre library (metadata.db + book files) and visualize it.
---

# Workflow: Process Calibre Library

1.  **Run Calibre pipeline**:
    ```bash
    uv run calibre_citations_pipeline.py <CALIBRE_LIBRARY_DIR> \
      --agent-max-concurrency 10
    # Outputs default to outputs/calibre_libs/<LIBRARY_DIR_NAME>
    ```

2.  **Register output for frontend**:
    ```bash
    uv run python scripts/register_dataset.py outputs/calibre_libs/<LIBRARY_DIR_NAME> --name "<DISPLAY_NAME>"
    ```

3.  **View**:
    Open the frontend. Large libraries may take a moment to load all nodes.
