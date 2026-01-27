---
name: calibre_query
description: Retrieve books from the local Calibre library based on natural language criteria (Author, Title, Tag, Language).
---

# Calibre Query Skill

This skill allows you to fetch books from the user's Calibre library into a staging area for processing.

## Tools
*   **`retrieve_books.py`**: CLI script to query and copy books.

## Usage

```bash
uv run .agent/skills/calibre_query/retrieve_books.py \
    --author "Eco" \
    --tag "non-fiction" \
    --lang "eng" \
    --library-path "/home/thiago/Onedrive/Ebooks Vault"
```

### Automatic Destination
The script automatically creates a timestamped folder in `input_books/libraries/` (e.g., `eco_non_fiction_20231027`) and copies the matching `.txt` files there.
