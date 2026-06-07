"""Generate a dataset of guaranteed-logically-solvable Minesweeper boards.

Each line of the output .jsonl file is one board:
  {
    "id":                  int,
    "rows":                int,
    "cols":                int,
    "num_mines":           int,
    "start":               [row, col],
    "mines":               [[row, col], ...],
    "grid":                [[int, ...], ...],   // -1 = mine, 0-8 = adjacency count
    "generation_attempts": int                  // boards tried before finding this one
  }

Usage examples
--------------
  python3 dataset.py -n 100 -o boards.jsonl
  python3 dataset.py -n 500 --rows 9 --cols 9 --mines 10 -o beginner.jsonl
  python3 dataset.py -n 50  --difficulty 4 -o phone.jsonl
  python3 dataset.py -n 200 --difficulty 2 --seed 42 -o intermediate.jsonl
"""
import argparse
import json
import sys
import time

from validate import generate_solvable

# ── Difficulty presets (rows, cols, mines) ─────────────────────────────────
PRESETS = {
    "1": (9,  9,  10),
    "2": (16, 16, 40),
    "3": (16, 30, 99),
    "4": (15,  9, 20),   # phone / 9:16
}


def board_to_record(board, start, board_id, attempts):
    grid = []
    for r in range(board.rows):
        row = []
        for c in range(board.cols):
            row.append(-1 if board.is_mine(r, c) else board.number(r, c))
        grid.append(row)

    return {
        "id":                  board_id,
        "rows":                board.rows,
        "cols":                board.cols,
        "num_mines":           len(board.mines),
        "start":               list(start),
        "mines":               sorted([r, c] for r, c in board.mines),
        "grid":                grid,
        "generation_attempts": attempts,
    }


def parse_args():
    p = argparse.ArgumentParser(
        description="Generate guaranteed-solvable Minesweeper boards.")
    p.add_argument("-n", "--count",      type=int, default=100,
                   help="Number of boards to generate (default: 100)")
    p.add_argument("-o", "--output",     default="-",
                   help="Output .jsonl file path, or '-' for stdout (default: -)")
    p.add_argument("--difficulty",       choices=PRESETS.keys(),
                   help="Preset: 1=Beginner, 2=Intermediate, 3=Expert, 4=Phone")
    p.add_argument("--rows",             type=int)
    p.add_argument("--cols",             type=int)
    p.add_argument("--mines",            type=int)
    p.add_argument("--start",            type=int, nargs=2, metavar=("ROW", "COL"),
                   help="Start cell (default: center)")
    p.add_argument("--seed",             type=int, default=None,
                   help="Base random seed (each board uses seed+id; default: random)")
    p.add_argument("--max-attempts",     type=int, default=1000,
                   help="Max rejected boards before giving up per board (default: 1000)")
    return p.parse_args()


def main():
    args = parse_args()

    # resolve dimensions
    if args.difficulty:
        rows, cols, mines = PRESETS[args.difficulty]
    else:
        rows  = args.rows  or 9
        cols  = args.cols  or 9
        mines = args.mines or 10

    if mines >= rows * cols:
        sys.exit(f"error: {mines} mines don't fit in a {rows}x{cols} board")

    start = tuple(args.start) if args.start else (rows // 2, cols // 2)

    # open output
    if args.output == "-":
        out = sys.stdout
        progress_stream = sys.stderr
    else:
        out = open(args.output, "w")
        progress_stream = sys.stderr

    def progress(msg, end="\n"):
        print(msg, end=end, file=progress_stream, flush=True)

    progress(f"Generating {args.count} boards  "
             f"({rows}x{cols}, {mines} mines, start={start})")
    if args.output != "-":
        progress(f"Output: {args.output}")
    progress("")

    t_total = time.monotonic()
    total_attempts = 0

    for board_id in range(args.count):
        seed = (args.seed + board_id) if args.seed is not None else None
        t0   = time.monotonic()

        rejected = [0]
        def on_attempt(attempt, _elapsed, _r=rejected):
            _r[0] = attempt
            progress(f"  [{board_id+1:>{len(str(args.count))}}/{args.count}]"
                     f"  attempt {attempt:4d}   {time.monotonic()-t0:.1f}s",
                     end="\r")

        board, attempts = generate_solvable(
            rows, cols, mines,
            start=start,
            seed=seed,
            max_attempts=args.max_attempts,
            on_attempt=on_attempt,
        )
        elapsed = time.monotonic() - t0
        total_attempts += attempts

        progress(f"  [{board_id+1:>{len(str(args.count))}}/{args.count}]"
                 f"  found in {attempts:4d} attempt(s)   {elapsed:.2f}s")

        record = board_to_record(board, start, board_id, attempts)
        out.write(json.dumps(record) + "\n")
        if out is not sys.stdout:
            out.flush()

    total_elapsed = time.monotonic() - t_total
    avg_attempts  = total_attempts / args.count
    progress(f"\nDone.  {args.count} boards in {total_elapsed:.1f}s  "
             f"(avg {avg_attempts:.1f} attempts/board)")

    if out is not sys.stdout:
        out.close()


if __name__ == "__main__":
    main()
