from __future__ import annotations
from enum import Enum, auto
from collections import deque
from generator import Board


class CellState(Enum):
    HIDDEN = auto()
    REVEALED = auto()
    FLAGGED = auto()


class GameState:
    """Tracks which cells have been revealed or flagged, independent of the board."""

    def __init__(self, board: Board):
        self.board = board
        self._state: dict[tuple[int, int], CellState] = {
            (r, c): CellState.HIDDEN
            for r in range(board.rows)
            for c in range(board.cols)
        }
        self.game_over = False
        self.won = False

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def state(self, r: int, c: int) -> CellState:
        return self._state[(r, c)]

    def is_hidden(self, r: int, c: int) -> bool:
        return self._state[(r, c)] == CellState.HIDDEN

    def is_revealed(self, r: int, c: int) -> bool:
        return self._state[(r, c)] == CellState.REVEALED

    def is_flagged(self, r: int, c: int) -> bool:
        return self._state[(r, c)] == CellState.FLAGGED

    def revealed_cells(self) -> list[tuple[int, int]]:
        return [pos for pos, s in self._state.items() if s == CellState.REVEALED]

    def hidden_cells(self) -> list[tuple[int, int]]:
        return [pos for pos, s in self._state.items() if s == CellState.HIDDEN]

    def flagged_cells(self) -> list[tuple[int, int]]:
        return [pos for pos, s in self._state.items() if s == CellState.FLAGGED]

    def cell_char(self, r: int, c: int) -> str:
        s = self._state[(r, c)]
        if s == CellState.HIDDEN:
            return "?"
        if s == CellState.FLAGGED:
            return "F"
        # revealed
        if self.board.is_mine(r, c):
            return "*"
        n = self.board.number(r, c)
        return str(n) if n > 0 else "."

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def reveal(self, r: int, c: int) -> bool:
        """Reveal a cell. Returns False if the cell was a mine (game over)."""
        if self._state[(r, c)] != CellState.HIDDEN:
            return True
        self._state[(r, c)] = CellState.REVEALED
        if self.board.is_mine(r, c):
            self.game_over = True
            return False
        # flood-fill zeros
        if self.board.number(r, c) == 0:
            self._flood_reveal(r, c)
        self._check_win()
        return True

    def _flood_reveal(self, r: int, c: int):
        queue = deque([(r, c)])
        visited = {(r, c)}
        while queue:
            cr, cc = queue.popleft()
            for nr, nc in self.board.neighbors(cr, cc):
                if (nr, nc) not in visited and self._state[(nr, nc)] == CellState.HIDDEN:
                    visited.add((nr, nc))
                    self._state[(nr, nc)] = CellState.REVEALED
                    if self.board.number(nr, nc) == 0:
                        queue.append((nr, nc))

    def flag(self, r: int, c: int):
        if self._state[(r, c)] == CellState.HIDDEN:
            self._state[(r, c)] = CellState.FLAGGED

    def unflag(self, r: int, c: int):
        if self._state[(r, c)] == CellState.FLAGGED:
            self._state[(r, c)] = CellState.HIDDEN

    def _check_win(self):
        for (r, c), s in self._state.items():
            if not self.board.is_mine(r, c) and s != CellState.REVEALED:
                return
        self.won = True
        self.game_over = True

    # ------------------------------------------------------------------
    # Constraint-relevant view (used by solver)
    # ------------------------------------------------------------------

    def constraint_cells(self) -> list[tuple[tuple[int, int], int, list[tuple[int, int]]]]:
        """For each revealed numbered cell, return (pos, effective_number, hidden_neighbors).

        effective_number = revealed number - count of flagged neighbors.
        Only cells with at least one hidden neighbor are included.
        """
        constraints = []
        for r, c in self.revealed_cells():
            n = self.board.number(r, c)
            if n < 0:
                continue  # shouldn't happen
            neighbors = self.board.neighbors(r, c)
            flagged = sum(1 for nb in neighbors if self.is_flagged(*nb))
            hidden = [nb for nb in neighbors if self.is_hidden(*nb)]
            if hidden:
                constraints.append(((r, c), n - flagged, hidden))
        return constraints
