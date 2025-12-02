# Data Sources & Pipeline Documentation

This directory contains the core datasets used to build the Book Graph.

## 1. Raw Data Sources

We utilize the **Goodreads Datasets** (likely from the UCSD Book Graph collection) as our primary source of truth for book metadata.

*   **`goodreads_books.json.gz`** (2.1 GB): The massive collection of book metadata. Contains titles, authors, publication years, ratings, and image URLs.
*   **`goodreads_book_authors.json.gz`** (18 MB): Metadata for authors (names, IDs).
*   **`goodreads_book_works.json.gz`** (75 MB): "Work" entities that group different editions of the same book.
*   **`enwiki-20251101-pages-articles-multistream.xml.bz2`** (25 GB): Full English Wikipedia dump, used for cross-referencing notable people and authors.

## 2. Transformations & Indexing

To enable real-time querying and graph construction, we transformed these massive raw files into efficient **SQLite FTS (Full-Text Search)** databases.

### A. Books Index (`books_index.db`)
*   **Source**: `goodreads_books.json.gz`
*   **Script**: [`scripts/build_goodreads_index.py`](../scripts/build_goodreads_index.py)
*   **Transformation**:
    1.  Iterated through the gzipped JSON stream.
    2.  Filtered for valid records (must have title and authors).
    3.  Inserted into a SQLite FTS5 virtual table `books_fts`.
*   **Schema**:
    ```sql
    CREATE VIRTUAL TABLE books_fts USING fts5(
        title,      -- Book title (indexed for search)
        authors,    -- Author names (indexed for search)
        data        -- Raw JSON blob containing full metadata
    );
    ```
*   **Purpose**: Allows instant lookup of "Cited Books" by title or author without scanning the 9GB JSON file.

### B. People Index (`wiki_people_index.db`)
*   **Source**: `enwiki-...xml.bz2`
*   **Scripts**:
    1.  [`scripts/filter_wiki_people.py`](../scripts/filter_wiki_people.py) (Extracts people from XML)
    2.  [`scripts/build_wiki_people_index.py`](../scripts/build_wiki_people_index.py) (Indexes them)
*   **Transformation**:
    1.  Parsed the XML dump to identify pages representing people.
    2.  Extracted metadata (birth/death dates, occupation).
    3.  Indexed into a SQLite database.
*   **Purpose**: Used to distinguish "Authors" from "Historical Figures" or other entities when processing citations.

## 4. Curated Metadata (The "Gold Standard")

We have enriched the raw Goodreads/Wikipedia data with a layer of manually curated and algorithmically cleaned metadata to ensure historical accuracy (e.g., correct BC dates for ancient authors).

*   **`original_publication_dates.json`**: A mapping of Goodreads IDs to **integer** publication years.
    *   **Source**: Scraped from Goodreads "original publication date" fields and manually corrected.
    *   **Corrections**: Includes fixes for ancient texts (e.g., Homer, Plato), "Year Unknown" issues, and integer normalization.
    *   **Usage**: Merged into `books_index.db` (column `original_publication_year`) for fast retrieval.

*   **`authors_metadata.json`**: A mapping of Author Names to birth/death years.
    *   **Source**: Extracted from Wikipedia and manually corrected for ancient/classical authors.
    *   **Usage**: Loaded by `bibliography_tool.py` as an **override layer**. If an author name matches exactly, these dates take precedence over `wiki_people_index.db`.

## 3. Usage in Pipeline

1.  **Extraction**: The pipeline reads your Calibre library.
2.  **Citation Analysis**: LLMs extract citations from your books.
3.  **Resolution**:
    *   **Source Books** are resolved against your local Calibre library.
    *   **Cited Books** (which you don't own) are looked up in `books_index.db` to fetch their covers, full author lists, and metadata.
4.  **Graph Generation**: The resolved data is combined to create the visualization.
