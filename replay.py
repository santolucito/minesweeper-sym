"""Minesweeper trace replay viewer.

Reads a JSONL trace file (one game per line) produced by either
  experiments/minesweeper/llm_eval.py  --save-traces <path>
  experiments/minesweeper/trace_gen.py  (LDT single-chain traces)

and replays each game move-by-move in the pygame UI at configurable speed.

Usage:
    python replay.py traces.jsonl
    python replay.py traces.jsonl --speed 5 --idx 3

Controls:
    Space           pause / resume
    Right / N       next puzzle
    Left / P        previous puzzle
    R               restart current puzzle from move 0
    Up / =          speed up (×1.5)
    Down / -        slow down (÷1.5)
    Q / Escape      quit
"""

import sys
import json
import argparse
import time
import pygame

from generator import Board
from game import GameState
from ui import (
    render_text, draw_raised, draw_sunken, draw_flag, draw_mine,
    CELL_HIDDEN, CELL_REVEALED, CELL_FLAG_BG, CELL_EXPLODED,
    NUMBER_COLORS, BG, TOOLBAR_BG,
)

# ── constants ──────────────────────────────────────────────────────────────────

CELL_SIZE  = 52          # pixels per cell
TOOLBAR_H  = 80          # top toolbar height
FPS        = 60

# Delay multipliers relative to base (1/speed seconds)
DELAY_NORMAL = 1.0
DELAY_ROUND  = 3.0       # pause between LDT rounds
DELAY_RESET  = 4.0       # hold game-over state before resetting

STATUS_OK   = (200, 200, 200)
STATUS_WIN  = ( 80, 220,  80)
STATUS_LOSE = (220,  80,  80)
STATUS_PART = (220, 180,  60)


# ── replay driver ──────────────────────────────────────────────────────────────

class ReplayApp:
    def __init__(self, traces: list[dict], speed: float = 4.0, start_idx: int = 0):
        self.traces  = traces
        self.speed   = speed          # base moves per second
        self.paused  = False

        pygame.init()
        pygame.display.set_caption("Minesweeper Replay")

        # Use geometry from the first trace
        t0 = traces[0]
        w  = t0["cols"] * CELL_SIZE
        h  = t0["rows"] * CELL_SIZE + TOOLBAR_H
        self.screen = pygame.display.set_mode((w, h))

        self.game_idx = start_idx
        self._load_game(start_idx)

    # ── game loading ───────────────────────────────────────────────────────────

    def _load_game(self, idx: int):
        self.game_idx = max(0, min(idx, len(self.traces) - 1))
        trace         = self.traces[self.game_idx]

        mines = frozenset(tuple(m) for m in trace["mines"])
        self.board = Board(rows=trace["rows"], cols=trace["cols"], mines=mines)
        self.game  = GameState(self.board)

        self.moves      = trace["moves"]
        self.move_idx   = 0
        self.t_next     = time.monotonic()  # time to apply next move
        self.completed  = False

        # Resize window if board dimensions changed
        w = trace["cols"] * CELL_SIZE
        h = trace["rows"] * CELL_SIZE + TOOLBAR_H
        if self.screen.get_size() != (w, h):
            self.screen = pygame.display.set_mode((w, h))

    def _restart(self):
        self._load_game(self.game_idx)

    # ── move application ───────────────────────────────────────────────────────

    def _move_delay(self, move: dict) -> float:
        base = 1.0 / max(self.speed, 0.1)
        t    = move["type"]
        if t == "round":
            return base * DELAY_ROUND
        if t == "reset":
            return base * DELAY_RESET
        return base * DELAY_NORMAL

    def _apply_move(self, move: dict):
        t = move["type"]
        if t == "reveal":
            r, c = move["pos"]
            # Skip cell moves while game is over — hold the explosion state
            # until the "reset" move fires.
            if not self.game.game_over and self.game.is_hidden(r, c):
                self.game.reveal(r, c)
        elif t == "flag":
            r, c = move["pos"]
            if not self.game.game_over and self.game.is_hidden(r, c):
                self.game.flag(r, c)
        elif t == "reset":
            # Recreate game state and apply only the initial reveal
            self.game = GameState(self.board)
            first = self.moves[0]
            if first["type"] == "reveal":
                self.game.reveal(*first["pos"])
        # "round" moves are timing-only — no state change

    def _advance(self):
        if self.paused or self.completed:
            return
        now = time.monotonic()
        if now < self.t_next:
            return
        if self.move_idx >= len(self.moves):
            self.completed = True
            return

        move = self.moves[self.move_idx]
        self._apply_move(move)
        self.t_next = now + self._move_delay(move)
        self.move_idx += 1

    # ── drawing ────────────────────────────────────────────────────────────────

    def _cell_rect(self, r: int, c: int) -> pygame.Rect:
        return pygame.Rect(c * CELL_SIZE, TOOLBAR_H + r * CELL_SIZE, CELL_SIZE, CELL_SIZE)

    def _draw_toolbar(self):
        trace = self.traces[self.game_idx]
        tw    = trace["cols"] * CELL_SIZE

        pygame.draw.rect(self.screen, TOOLBAR_BG, (0, 0, tw, TOOLBAR_H))

        # ── row 1: source label (left) + outcome (right) ──────────────
        source  = trace.get("source", "?").upper()
        model   = trace.get("model", "?")
        short_m = model.split("/")[-1] if "/" in model else model
        label   = f"{source}: {short_m}"
        lsurf   = render_text(label, 14, (160, 200, 255), bold=True)
        self.screen.blit(lsurf, (10, 8))

        outcome = trace.get("outcome", "?")
        ocol    = (STATUS_WIN if outcome == "correct" else
                   STATUS_LOSE if outcome == "wrong" else STATUS_PART)
        osurf   = render_text(outcome.upper(), 14, ocol, bold=True)
        self.screen.blit(osurf, (tw - osurf.get_width() - 10, 8))

        # ── progress bar ──────────────────────────────────────────────
        pct   = self.move_idx / max(len(self.moves), 1)
        bar_w = tw - 20
        pygame.draw.rect(self.screen, (50, 50, 70), (10, 30, bar_w, 7), border_radius=3)
        fill  = max(4, int(bar_w * pct))
        pygame.draw.rect(self.screen, (90, 150, 240), (10, 30, fill, 7), border_radius=3)

        # ── row 2: move counter (left) + puzzle counter (right) ───────
        mtxt  = f"move {self.move_idx}/{len(self.moves)}"
        msurf = render_text(mtxt, 12, (150, 150, 160))
        self.screen.blit(msurf, (10, 42))

        ptxt  = f"puzzle {self.game_idx + 1}/{len(self.traces)}"
        psurf = render_text(ptxt, 12, (150, 150, 160))
        self.screen.blit(psurf, (tw - psurf.get_width() - 10, 42))

        # ── row 3: speed + hint ───────────────────────────────────────
        spd_label = f"{'⏸ PAUSED' if self.paused else '▶'} {self.speed:.1f} moves/s"
        spd_col   = (80, 220, 80) if self.paused else (220, 200, 80)
        ssurf     = render_text(spd_label, 12, spd_col, bold=True)
        self.screen.blit(ssurf, (10, 60))

        hint  = "Spc=pause  N/P=next/prev  R=restart  ↑↓=speed  Esc=quit"
        hsurf = render_text(hint, 11, (100, 100, 110))
        self.screen.blit(hsurf, (tw - hsurf.get_width() - 10, 60))

    def _draw_grid(self):
        trace = self.traces[self.game_idx]
        rows, cols = trace["rows"], trace["cols"]

        for r in range(rows):
            for c in range(cols):
                rect = self._cell_rect(r, c)
                cx, cy = rect.centerx, rect.centery

                if self.game.is_revealed(r, c):
                    draw_sunken(self.screen, rect, CELL_REVEALED)
                    if self.board.is_mine(r, c):
                        pygame.draw.rect(self.screen, CELL_EXPLODED, rect)
                        draw_mine(self.screen, cx, cy, CELL_SIZE, (20, 20, 20))
                    else:
                        n = self.board.number(r, c)
                        if n > 0:
                            color = NUMBER_COLORS.get(n, (0, 0, 0))
                            sz    = max(14, CELL_SIZE // 2)
                            surf  = render_text(str(n), sz, color, bold=True)
                            self.screen.blit(surf, (cx - surf.get_width() // 2,
                                                    cy - surf.get_height() // 2))
                elif self.game.is_flagged(r, c):
                    draw_raised(self.screen, rect, CELL_FLAG_BG)
                    draw_flag(self.screen, cx, cy, CELL_SIZE - 10)
                else:
                    draw_raised(self.screen, rect, CELL_HIDDEN)

        # On game-over, reveal all un-flagged mines
        if self.game.game_over and not self.game.won:
            for r_m, c_m in self.board.mines:
                if not self.game.is_flagged(r_m, c_m) and not self.game.is_revealed(r_m, c_m):
                    rect = self._cell_rect(r_m, c_m)
                    draw_raised(self.screen, rect, CELL_REVEALED)
                    draw_mine(self.screen, rect.centerx, rect.centery, CELL_SIZE)

    def _draw(self):
        self.screen.fill(BG)
        self._draw_toolbar()
        self._draw_grid()

    # ── main loop ──────────────────────────────────────────────────────────────

    def run(self):
        clock = pygame.time.Clock()
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif event.type == pygame.KEYDOWN:
                    k = event.key
                    if k in (pygame.K_q, pygame.K_ESCAPE):
                        pygame.quit()
                        sys.exit()
                    elif k == pygame.K_SPACE:
                        self.paused = not self.paused
                        if not self.paused:
                            # Reset the next-move timer so we don't skip ahead
                            self.t_next = time.monotonic()
                    elif k in (pygame.K_n, pygame.K_RIGHT):
                        self._load_game(self.game_idx + 1)
                    elif k in (pygame.K_p, pygame.K_LEFT):
                        self._load_game(self.game_idx - 1)
                    elif k == pygame.K_r:
                        self._restart()
                    elif k in (pygame.K_UP, pygame.K_EQUALS, pygame.K_PLUS):
                        self.speed = min(self.speed * 1.5, 30.0)
                    elif k in (pygame.K_DOWN, pygame.K_MINUS):
                        self.speed = max(self.speed / 1.5, 0.3)

            self._advance()
            self._draw()
            pygame.display.flip()
            clock.tick(FPS)


# ── entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Replay Minesweeper solver traces in pygame."
    )
    parser.add_argument("traces", help="Path to .jsonl trace file")
    parser.add_argument("--speed", type=float, default=4.0,
                        help="Base moves per second (default 4)")
    parser.add_argument("--idx", type=int, default=0,
                        help="Starting puzzle index (0-based)")
    args = parser.parse_args()

    with open(args.traces) as fh:
        traces = [json.loads(line) for line in fh if line.strip()]
    if not traces:
        sys.exit("No traces found in file.")

    print(f"Loaded {len(traces)} trace(s) from {args.traces}")
    ReplayApp(traces, speed=args.speed, start_idx=args.idx).run()


if __name__ == "__main__":
    main()
