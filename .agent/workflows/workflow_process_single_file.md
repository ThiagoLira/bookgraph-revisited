---
description: Process a single text file to extract citations and visualize it.
---

# Workflow: Process Single File

1.  **Run extraction and resolution**:
    ```bash
    uv run run_single_file.py <INPUT_TXT_PATH> \
      --output-dir outputs/single_runs/<BOOK_ID> \
      --book-title "<TITLE>" \
      --author "<AUTHOR>" \
      --goodreads-id <BOOK_ID>
    ```

2.  **Register output for frontend**:
    ```bash
    uv run python scripts/register_dataset.py outputs/single_runs/<BOOK_ID> --name "<DISPLAY_NAME>"
    ```

3.  **View**:
    Open the frontend (e.g. `http://localhost:8000`) and select your new dataset.
