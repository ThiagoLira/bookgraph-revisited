#!/usr/bin/env python3
import argparse
import json
import mmap
import multiprocessing as mp
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_JSON_PATH = "goodreads_data/goodreads_books.json"
# Middle entry from tests: "El Espejo de mi Alma"
MIDDLE_BOOK_ID = "12841265"

# ---------- Line-aligned chunking ----------


def line_chunk_boundaries(mm: mmap.mmap, workers: int) -> List[int]:
    """
    Return sorted byte positions that mark chunk *starts* aligned to line boundaries.
    boundaries[0] = 0, boundaries[-1] = file_size.
    Each chunk is [boundaries[i], boundaries[i+1]).
    """
    file_size = mm.size()
    workers = max(1, workers)
    boundaries = [0]

    # Find up to workers-1 interior boundaries: for each approximate offset,
    # advance to the next '\n' and start the next chunk at pos+1.
    for i in range(1, workers):
        approx = (file_size * i) // workers
        if approx >= file_size:
            break
        pos = mm.find(b"\n", approx)  # newline ending a line
        if pos == -1:
            # No more newlines; rest becomes one chunk
            break
        start_of_next_line = pos + 1
        if start_of_next_line < file_size and start_of_next_line > boundaries[-1]:
            boundaries.append(start_of_next_line)

    if boundaries[-1] != file_size:
        boundaries.append(file_size)

    # Dedup & ensure strictly increasing
    out = []
    last = -1
    for b in sorted(boundaries):
        if b > last:
            out.append(b)
            last = b
    if out[-1] != file_size:
        out.append(file_size)
    return out

# ---------- Workers ----------


def worker_scan(path: str, start: int, end: int, target_id: str,
                found_event: mp.Event, result_q: mp.Queue) -> None:
    target_bytes = target_id.encode("utf-8")
    try:
        with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            pos = start
            mm.seek(pos)
            while not found_event.is_set() and pos < end:
                line = mm.readline()
                if not line:
                    break
                pos_next = mm.tell()
                # Hard stop at chunk end: if the read crossed end, we still got a full
                # line that *belongs* to this chunk since chunk ends are newline-aligned.
                # But guard anyway:
                if pos_next > end and end != mm.size():
                    # If end isn't EOF, we shouldn't have crossed it—trim and continue.
                    line = line[:max(0, len(line) - (pos_next - end))]
                s = line.strip()
                if not s:
                    pos = pos_next
                    continue
                # Fast filter: only parse if it could match
                if target_bytes in s:
                    try:
                        rec = json.loads(s.decode("utf-8", errors="replace"))
                    except json.JSONDecodeError:
                        pos = pos_next
                        continue
                    rec_id = str(rec.get("book_id") or rec.get("id") or "")
                    if rec_id == target_id:
                        if not found_event.is_set():
                            found_event.set()
                            result_q.put(rec)
                        return
                pos = pos_next
    except Exception as e:
        if not found_event.is_set():
            result_q.put({"__error__": f"Worker {start}-{end} exception: {e}"})


def main():
    ap = argparse.ArgumentParser(
        description="Benchmark legacy multiprocessing lookup against the middle test entry."
    )
    ap.add_argument(
        "--json-path",
        default=DEFAULT_JSON_PATH,
        help="Path to goodreads_books.json (JSONL)",
    )
    ap.add_argument(
        "--book-id",
        default=MIDDLE_BOOK_ID,
        help="Goodreads book_id to search for (default: middle unit test entry).",
    )
    ap.add_argument(
        "-w",
        "--workers",
        type=int,
        default=20,
        help="Number of processes (default: 20)",
    )
    args = ap.parse_args()

    json_path = Path(args.json_path)
    if not json_path.exists():
        print(f"Error: dataset not found at {json_path}", file=sys.stderr)
        sys.exit(2)

    start_time = time.perf_counter()

    with open(args.json_path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        bounds = line_chunk_boundaries(mm, args.workers)

    # Spawn workers for each [start, end)
    ctx = mp.get_context("fork" if sys.platform != "win32" else "spawn")
    found_event = ctx.Event()
    result_q = ctx.Queue(maxsize=1)

    procs = []
    for i in range(len(bounds) - 1):
        start, end = bounds[i], bounds[i+1]
        p = ctx.Process(target=worker_scan,
                        args=(args.json_path, start, end,
                              args.book_id, found_event, result_q),
                        daemon=True)
        p.start()
        procs.append(p)

    rec = None
    # Wait until one returns a result or all exit
    while rec is None and any(p.is_alive() for p in procs):
        try:
            msg = result_q.get(timeout=0.2)
            if isinstance(msg, dict) and "__error__" in msg:
                # Optional: print(msg["__error__"], file=sys.stderr)
                pass
            else:
                rec = msg
                found_event.set()
                break
        except Exception:
            pass

    # Stop everyone else
    for p in procs:
        if p.is_alive():
            p.terminate()
    for p in procs:
        p.join(timeout=1.0)

    elapsed = time.perf_counter() - start_time
    if rec is None:
        print(
            f"[MP_OLD] book_id {args.book_id} not found after {elapsed:.3f}s",
            file=sys.stderr,
        )
        sys.exit(3)

    title = rec.get("title") or rec.get("title_without_series") or "<unknown>"
    print(
        f"[MP_OLD] Found '{title}' (ID {args.book_id}) "
        f"in {elapsed:.3f}s using {args.workers} processes."
    )


if __name__ == "__main__":
    main()
