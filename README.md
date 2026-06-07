# Minesweeper Symbolic Solver

A Minesweeper game where every deduction is made by an SMT solver ([CVC5](https://cvc5.github.io/)) rather than hand-coded logic. The solver proves cells safe or mine by checking satisfiability — no heuristics, no guessing (when the board allows it).

## How it works

Each hidden cell is an integer variable `x(r,c) ∈ {0,1}` where `1 = mine`.  
Every revealed numbered cell contributes one linear constraint:

```
sum of x(r,c) for hidden neighbours  =  revealed_number - flagged_neighbours
```

Together these form the formula **φ** (in the quantifier-free linear integer arithmetic logic, QF_LIA).

To determine whether a cell is safe or a mine, CVC5 runs two queries per cell using push/pop:

| Query | Result | Conclusion |
|---|---|---|
| `SAT( φ ∧ x(r,c) = 1 )` | UNSAT | no valid board has that cell as a mine → **safe** |
| `SAT( φ ∧ x(r,c) = 0 )` | UNSAT | no valid board has that cell as safe → **mine** |

If both queries return SAT, the cell is ambiguous — a guess would be required.

## Features

- **Pygame UI** with solver hints, formula overlay, and multiple difficulty presets
- **Guaranteed-solvable mode** — rejection-samples boards until one is fully solvable by logic alone (no guessing required at any point)
- **Formula overlay** (press `F`) showing the live SMT variables, constraints, proof strategy, and per-cell query results
- **Dataset generator** — exports `.jsonl` files of guaranteed-solvable boards for ML / analysis
- **Phone / 9:16 preset** (450×800) suitable for recording

## Install

```bash
pip install cvc5 pygame pillow
```

Requires Python 3.11+.

## Run

### Interactive game

```bash
python3 ui.py
```

| Key | Action |
|---|---|
| Left-click | Reveal cell |
| Right-click | Flag / unflag |
| `S` | Run solver — highlights safe (green) and mine (red) cells |
| `A` | Auto-apply all current solver deductions |
| `F` | Toggle SMT formula overlay (scroll with ↑↓ or wheel) |
| `G` | Toggle guaranteed-solvable mode (no guessing required) |
| `R` | New game |
| `1` / `2` / `3` / `4` | Beginner / Intermediate / Expert / Phone (9:16) |

### Headless auto-play

```bash
python3 main.py          # seed 42
python3 main.py 123      # custom seed
```

### Generate a dataset

```bash
# 100 phone-preset boards → phone.jsonl
python3 dataset.py -n 100 --difficulty 4 -o phone.jsonl

# 500 beginner boards, reproducible
python3 dataset.py -n 500 --difficulty 1 --seed 42 -o beginner.jsonl

# custom dimensions
python3 dataset.py -n 200 --rows 9 --cols 9 --mines 10 -o custom.jsonl
```

Each `.jsonl` record:

```json
{
  "id": 0,
  "rows": 15, "cols": 9, "num_mines": 20,
  "start": [7, 4],
  "mines": [[2,4], [3,0], ...],
  "grid": [[0,0,1,...], ...],
  "generation_attempts": 2
}
```

`grid` values: `-1` = mine, `0–8` = adjacency count.

## Project structure

| File | Purpose |
|---|---|
| `generator.py` | Random board generation with safe-start guarantee |
| `game.py` | Game state — reveal, flag, flood-fill, constraint extraction |
| `solver.py` | CVC5 QF_LIA encoding and push/pop UNSAT queries |
| `validate.py` | Solvability check and rejection-sampling generator |
| `dataset.py` | CLI dataset generator |
| `ui.py` | Pygame frontend |
| `main.py` | Headless auto-play demo |
