"""Demo: generate a board, reveal the safe-start cell, then drive the solver."""
import sys
from generator import generate
from game import GameState
from solver import solve


def auto_play(rows=9, cols=9, num_mines=10, seed=42):
    start = (rows // 2, cols // 2)
    board = generate(rows, cols, num_mines, seed=seed, safe_start=start)
    game = GameState(board)

    print("=== Generated board (solution) ===")
    print(board.display())

    # Reveal the safe starting cell
    game.reveal(*start)
    print(f"\n=== After revealing {start} ===")
    print(board.display(game))

    step = 0
    while not game.game_over:
        result = solve(game)

        if not result.safe and not result.mines:
            print("\nSolver: no deductions possible, stopping.")
            break

        acted = False
        for pos in result.mines:
            if game.is_hidden(*pos):
                print(f"  Flag mine at {pos}")
                game.flag(*pos)
                acted = True

        for pos in result.safe:
            if game.is_hidden(*pos):
                print(f"  Reveal safe cell {pos}")
                game.reveal(*pos)
                acted = True
                if game.game_over:
                    break

        if not acted:
            break

        step += 1
        print(f"\n=== After step {step} ===")
        print(board.display(game))

    if game.won:
        print("\nPuzzle SOLVED!")
    elif game.game_over:
        print("\nGame over (hit a mine).")
    else:
        print("\nSolver stalled — remaining cells undetermined.")

    remaining = game.hidden_cells()
    if remaining:
        print(f"  {len(remaining)} hidden cells remain.")


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    auto_play(seed=seed)
