#!/usr/bin/env python3
"""ingest_books.py — End-to-end driver to add book(s) to the BookGraph frontend.

Wraps the manual workflow:
  1. run_single_file.py  (extract citations -> match Goodreads/Wikipedia -> enrich)
  2. register_dataset.py --build  (copy into frontend/data/<slug> + offline bake)

Loads OPENROUTER_API_KEY from .env automatically. Default model is whatever
run_single_file.py defaults to (currently deepseek/deepseek-v4-flash).

Single book:
  uv run python scripts/ingest_books.py \
      --input gutenberg_downloads/hobbes_leviathan__pg3207.txt \
      --title "Leviathan" --author "Thomas Hobbes" \
      --name "Hobbes: Leviathan" --build

Many books into ONE interconnected library dataset (recommended for a batch):
  uv run python scripts/ingest_books.py \
      --manifest gutenberg_downloads/books.tsv \
      --output-dir outputs/single_runs/gutenberg_classics \
      --name "Gutenberg Classics" --build --workers 3

Manifest format: TSV, one row per book, columns:  filepath <TAB> title <TAB> author
A book_id is derived from a trailing pgNNNNN / _NNNNN in the filename, else the stem.
"""
from __future__ import annotations
import argparse, asyncio, os, re, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load_env_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def book_id_from(path: Path) -> str:
    m = re.search(r'(?:pg|_)(\d+)\.txt$', path.name)
    return f"pg{m.group(1)}" if m else path.stem


def run_one(inp: Path, title: str, author: str, out_dir: Path, model: str | None, env: dict) -> bool:
    bid = book_id_from(inp)
    cmd = [
        "uv", "run", "python", str(REPO / "run_single_file.py"), str(inp),
        "--book-title", title, "--author", author,
        "--goodreads-id", bid, "--output-dir", str(out_dir),
    ]
    if model:
        cmd += ["--model", model]
    print(f"  ▶ {title} ({author}) [{bid}]", flush=True)
    r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True)
    final = out_dir / "final_citations_metadata_goodreads" / f"{bid}.json"
    ok = r.returncode == 0 and final.exists()
    if not ok:
        print(f"  ✗ FAILED {title}\n{r.stdout[-1500:]}\n{r.stderr[-800:]}", flush=True)
    else:
        print(f"  ✓ {title} -> {final.name}", flush=True)
    return ok


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", type=Path, help="Single book .txt")
    p.add_argument("--title"); p.add_argument("--author")
    p.add_argument("--manifest", type=Path, help="TSV: filepath<TAB>title<TAB>author")
    p.add_argument("--output-dir", type=Path, default=REPO / "outputs" / "single_runs" / "ingest_run")
    p.add_argument("--name", help="Display name for the frontend dataset")
    p.add_argument("--model", default=None, help="Override LLM (default: run_single_file default)")
    p.add_argument("--workers", type=int, default=1, help="Parallel books (each already uses internal concurrency)")
    p.add_argument("--build", action="store_true", help="Register + offline bake after processing")
    p.add_argument("--no-register", action="store_true", help="Skip register/bake (process only)")
    return p.parse_args()


def main():
    a = parse_args()
    key = load_env_key()
    if not key:
        print("ERROR: OPENROUTER_API_KEY not found in env or .env"); sys.exit(1)
    env = {**os.environ, "OPENROUTER_API_KEY": key}

    jobs: list[tuple[Path, str, str]] = []
    if a.manifest:
        for ln in a.manifest.read_text().splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            parts = ln.split("\t")
            if len(parts) < 3:
                print(f"  ! skip malformed manifest row: {ln}"); continue
            fp = Path(parts[0]);  fp = fp if fp.is_absolute() else REPO / fp
            jobs.append((fp, parts[1], parts[2]))
    elif a.input and a.title and a.author:
        fp = a.input if a.input.is_absolute() else REPO / a.input
        jobs.append((fp, a.title, a.author))
    else:
        print("ERROR: provide --manifest, or --input/--title/--author"); sys.exit(1)

    a.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Ingesting {len(jobs)} book(s) -> {a.output_dir} (workers={a.workers})")

    results = []
    if a.workers <= 1:
        for fp, t, au in jobs:
            results.append(run_one(fp, t, au, a.output_dir, a.model, env))
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=a.workers) as ex:
            futs = [ex.submit(run_one, fp, t, au, a.output_dir, a.model, env) for fp, t, au in jobs]
            results = [f.result() for f in futs]

    ok = sum(results)
    print(f"\nProcessed {ok}/{len(jobs)} books successfully.")

    if a.build and not a.no_register:
        name = a.name or a.output_dir.name
        print(f"\nRegistering + baking dataset '{name}' ...")
        subprocess.run([
            "uv", "run", "python", str(REPO / "scripts" / "register_dataset.py"),
            str(a.output_dir), "--name", name, "--build",
        ], cwd=REPO, env=env)


if __name__ == "__main__":
    main()
