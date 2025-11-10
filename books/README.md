# Books Directory

This directory contains the source text files (books) used for citation extraction.

## Current Books

- **Justice: What's the Right Thing to Do?** by Michael J. Sandel (591KB)
- **Where the Stress Falls** by Susan Sontag (680KB)

## Usage

Books in this directory can be processed using:

```bash
# Using the profiling script
./run_profiled_single.sh "books/your-book.txt"

# Using the CLI directly
uv run python run_single_file.py "books/your-book.txt" --chunk-size 50 --max-concurrency 30
```

## Note

This directory is gitignored to avoid versioning large text files. Add your books here locally for processing.
