---
name: goodreads_lookup
description: Lookup Goodreads Book IDs by Title and Author using the local SQL database.
---

# Goodreads Lookup Skill

This skill allows you to query the local `books_index.db` to find the Goodreads ID for a specific book. This is useful when you need to resolve a citation manually or debug why a book isn't being found.

## Tools

*   **`lookup_book.py`**: A CLI script to search for books.

## Usage

Run the script from the repository root:

```bash
uv run .agent/skills/goodreads_lookup/lookup_book.py --title "Book Title" --author "Author Name"
```

### Arguments

*   `--title`: (Required) The title (or partial title) of the book.
*   `--author`: (Optional) The author's name. If provided, searches for books by this author containing the title. If omitted, searches matches by title only.
*   `--limit`: (Optional) Max results (default: 10).

### Example Output

```text
Found 1 matches for 'The Mirror of the Sea' by 'Joseph Conrad':

1. The Mirror of the Sea (ID: 441880)
   Author: Joseph Conrad
   Year: 1906
   Match Score: 5.2
```
