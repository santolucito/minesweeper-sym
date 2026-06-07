"""CVC5-backed symbolic Minesweeper solver.

For each unrevealed cell we introduce an integer variable x in {0,1}
(1 = mine).  For each revealed numbered cell we assert:
    sum(x_nb for nb in hidden_neighbors) = effective_number

A cell is provably SAFE  if (constraints ∧ x=1) is UNSAT.
A cell is provably a MINE if (constraints ∧ x=0) is UNSAT.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto

import cvc5
from cvc5 import Kind

from game import GameState


class Verdict(Enum):
    SAFE = auto()   # provably not a mine
    MINE = auto()   # provably a mine
    UNKNOWN = auto()


@dataclass
class SolverResult:
    safe: list[tuple[int, int]]   # cells that are definitely safe
    mines: list[tuple[int, int]]  # cells that are definitely mines


def _build_base_solver(game: GameState) -> tuple[cvc5.Solver, dict[tuple[int, int], cvc5.Term]]:
    """Create a CVC5 solver loaded with all constraints from the current game state."""
    tm = cvc5.TermManager()
    solver = cvc5.Solver(tm)
    solver.setOption("produce-models", "true")
    solver.setLogic("QF_LIA")  # quantifier-free linear integer arithmetic

    int_sort = tm.getIntegerSort()

    # Create one integer variable per hidden cell
    hidden = game.hidden_cells()
    variables: dict[tuple[int, int], cvc5.Term] = {}
    for r, c in hidden:
        var = tm.mkConst(int_sort, f"x_{r}_{c}")
        variables[(r, c)] = var
        # 0 <= x <= 1
        solver.assertFormula(
            tm.mkTerm(Kind.GEQ, var, tm.mkInteger(0))
        )
        solver.assertFormula(
            tm.mkTerm(Kind.LEQ, var, tm.mkInteger(1))
        )

    # Add neighbour-sum constraints for every revealed numbered cell
    for _pos, effective_n, hidden_neighbors in game.constraint_cells():
        terms = [variables[nb] for nb in hidden_neighbors if nb in variables]
        if not terms:
            continue
        if len(terms) == 1:
            total = terms[0]
        else:
            total = tm.mkTerm(Kind.ADD, *terms)
        solver.assertFormula(
            tm.mkTerm(Kind.EQUAL, total, tm.mkInteger(effective_n))
        )

    return solver, variables


def solve(game: GameState) -> SolverResult:
    """Query CVC5 for each hidden cell to determine if it is safe or a mine."""
    solver, variables = _build_base_solver(game)

    # First check that the base constraints are satisfiable at all
    base_result = solver.checkSat()
    if base_result.isUnsat():
        # Constraint contradiction — no valid deduction possible
        return SolverResult(safe=[], mines=[])

    tm = solver.getTermManager()

    safe: list[tuple[int, int]] = []
    mines: list[tuple[int, int]] = []

    for pos, var in variables.items():
        # --- check if definitely SAFE (x=1 impossible) ---
        solver.push()
        solver.assertFormula(
            tm.mkTerm(Kind.EQUAL, var, tm.mkInteger(1))
        )
        result = solver.checkSat()
        solver.pop()
        if result.isUnsat():
            safe.append(pos)
            continue

        # --- check if definitely a MINE (x=0 impossible) ---
        solver.push()
        solver.assertFormula(
            tm.mkTerm(Kind.EQUAL, var, tm.mkInteger(0))
        )
        result = solver.checkSat()
        solver.pop()
        if result.isUnsat():
            mines.append(pos)

    return SolverResult(safe=sorted(safe), mines=sorted(mines))


def verdict(game: GameState, r: int, c: int) -> Verdict:
    """Return the verdict for a single cell (convenience wrapper)."""
    result = solve(game)
    pos = (r, c)
    if pos in result.safe:
        return Verdict.SAFE
    if pos in result.mines:
        return Verdict.MINE
    return Verdict.UNKNOWN
