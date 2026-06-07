import random
from dataclasses import dataclass, field
from typing import Iterator


def _neighbors(r: int, c: int, rows: int, cols: int) -> Iterator[tuple[int, int]]:
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                yield nr, nc


@dataclass
class Board:
    rows: int
    cols: int
    mines: frozenset[tuple[int, int]]
    # number of adjacent mines for each non-mine cell
    numbers: dict[tuple[int, int], int] = field(default_factory=dict)

    def __post_init__(self):
        if not self.numbers:
            for r in range(self.rows):
                for c in range(self.cols):
                    if (r, c) not in self.mines:
                        count = sum(
                            1
                            for nb in _neighbors(r, c, self.rows, self.cols)
                            if nb in self.mines
                        )
                        self.numbers[(r, c)] = count

    def neighbors(self, r: int, c: int) -> list[tuple[int, int]]:
        return list(_neighbors(r, c, self.rows, self.cols))

    def is_mine(self, r: int, c: int) -> bool:
        return (r, c) in self.mines

    def number(self, r: int, c: int) -> int:
        return self.numbers.get((r, c), -1)

    def display(self, game_state=None) -> str:
        """Print the board. If game_state is provided, show revealed info."""
        lines = []
        header = "   " + " ".join(f"{c:2}" for c in range(self.cols))
        lines.append(header)
        lines.append("   " + "--" * self.cols)
        for r in range(self.rows):
            row = f"{r:2}|"
            for c in range(self.cols):
                if game_state is None:
                    if (r, c) in self.mines:
                        row += " *"
                    else:
                        n = self.numbers[(r, c)]
                        row += f" {n}" if n > 0 else "  "
                else:
                    row += " " + game_state.cell_char(r, c)
            lines.append(row)
        return "\n".join(lines)


def generate(
    rows: int = 9,
    cols: int = 9,
    num_mines: int = 10,
    seed: int | None = None,
    safe_start: tuple[int, int] | None = None,
) -> Board:
    """Generate a random minesweeper board.

    If safe_start is given, mines are placed so that cell is guaranteed safe
    (standard minesweeper first-click guarantee).
    """
    rng = random.Random(seed)
    all_cells = [(r, c) for r in range(rows) for c in range(cols)]
    excluded = set()
    if safe_start is not None:
        sr, sc = safe_start
        excluded.add(safe_start)
        excluded.update(_neighbors(sr, sc, rows, cols))
    candidates = [cell for cell in all_cells if cell not in excluded]
    if num_mines > len(candidates):
        raise ValueError(
            f"Cannot place {num_mines} mines with only {len(candidates)} eligible cells"
        )
    mines = frozenset(rng.sample(candidates, num_mines))
    return Board(rows=rows, cols=cols, mines=mines)
