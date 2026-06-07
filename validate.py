"""Board solvability validation and guaranteed-solvable generation.

A board is logically solvable from `start` if the CVC5 solver can deduce
every cell — mine or safe — without ever needing to guess.  We verify this
by simulating a complete game: reveal `start`, then repeatedly ask the solver
for deductions until either the board is cleared or the solver is stuck.
"""
from generator import Board, generate
from game import GameState
from solver import solve


def is_logically_solvable(board: Board, start: tuple[int, int]) -> bool:
    """Return True iff the board can be fully solved by logic from `start`."""
    game = GameState(board)
    game.reveal(*start)
    if game.game_over and not game.won:
        return False  # start was a mine (shouldn't happen with safe_start)

    while True:
        if game.won:
            return True
        if not game.hidden_cells():
            return game.won

        result = solve(game)

        if not result.safe and not result.mines:
            return False  # solver is stuck — a guess would be required

        for pos in result.mines:
            if game.is_hidden(*pos):
                game.flag(*pos)
        for pos in result.safe:
            if game.is_hidden(*pos):
                game.reveal(*pos)
                if game.game_over and not game.won:
                    return False  # shouldn't happen; just in case


def generate_solvable(
    rows: int,
    cols: int,
    num_mines: int,
    start: tuple[int, int] | None = None,
    seed: int | None = None,
    max_attempts: int = 1000,
    on_attempt: callable = None,
) -> tuple[Board, int]:
    """Return (board, attempts) where board is guaranteed logically solvable.

    on_attempt(attempt, elapsed_seconds) is called after every failed attempt,
    allowing the caller to update a progress display.
    """
    import time
    if start is None:
        start = (rows // 2, cols // 2)

    t0 = time.monotonic()
    rng_seed = seed
    for attempt in range(1, max_attempts + 1):
        board = generate(rows, cols, num_mines,
                         seed=rng_seed, safe_start=start)
        if is_logically_solvable(board, start):
            return board, attempt
        if on_attempt is not None:
            on_attempt(attempt, time.monotonic() - t0)
        if rng_seed is not None:
            rng_seed += 1

    raise RuntimeError(
        f"Could not find a logically solvable board in {max_attempts} attempts"
    )
