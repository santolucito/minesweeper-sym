"""Pygame Minesweeper UI with CVC5 solver integration.

Controls:
  Left-click          reveal cell
  Right-click         flag / unflag cell
  S                   run one solver step (shows green=safe, red=mine hints)
  A                   auto-apply all current solver hints
  F                   toggle SMT formula overlay (scroll with ↑/↓ or wheel)
  R                   new game (same difficulty)
  1/2/3               switch difficulty: 1=Beginner, 2=Intermediate, 3=Expert
"""
import sys
import time
import threading
import pygame
from PIL import Image, ImageDraw, ImageFont as PILFont
from generator import generate
from game import GameState
from solver import SolverResult, solve
from validate import generate_solvable


# ---------------------------------------------------------------------------
# PIL-based text rendering (workaround for pygame.font circular import on
# Python 3.14 + pygame 2.6.1)
# ---------------------------------------------------------------------------
_FONT_CACHE: dict[tuple, pygame.Surface] = {}

def _pil_font(size: int, bold: bool = False) -> PILFont.ImageFont:
    # Prefer Menlo (macOS terminal default, full Unicode math coverage).
    # Fall back through other monospace options to Courier New.
    menlo_index = 1 if bold else 0
    candidates = [
        ("/System/Library/Fonts/Menlo.ttc",                          {"index": menlo_index}),
        ("/System/Library/Fonts/SFNSMono.ttf",                       {}),
        ("/System/Library/Fonts/Supplemental/PTMono.ttc",            {}),
        ("/System/Library/Fonts/Supplemental/Courier New Bold.ttf"
         if bold else
         "/System/Library/Fonts/Supplemental/Courier New.ttf",       {}),
    ]
    for path, kwargs in candidates:
        try:
            return PILFont.truetype(path, size, **kwargs)
        except OSError:
            pass
    return PILFont.load_default()


def render_text(text: str, size: int, color: tuple,
                bold: bool = False) -> pygame.Surface:
    key = (text, size, color, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    font = _pil_font(size, bold)
    # measure
    dummy = Image.new("RGBA", (1, 1))
    bbox = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0] + 2, bbox[3] - bbox[1] + 2
    img = Image.new("RGBA", (max(w, 1), max(h, 1)), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((-bbox[0] + 1, -bbox[1] + 1), text,
                             font=font, fill=color + (255,))
    surf = pygame.image.frombuffer(img.tobytes(), img.size, "RGBA")
    _FONT_CACHE[key] = surf
    return surf

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
BG          = (  0,   0,   0)
TOOLBAR_BG  = ( 30,  30,  30)
BORDER_DARK = (128, 128, 128)
BORDER_LIGHT= (255, 255, 255)

CELL_HIDDEN    = (189, 189, 189)
CELL_REVEALED  = (224, 224, 224)
CELL_HINT_SAFE = ( 80, 200,  80)
CELL_HINT_MINE = (220,  60,  60)
CELL_FLAG_BG   = (189, 189, 189)
CELL_EXPLODED  = (220,  80,  80)

NUMBER_COLORS = {
    1: ( 25,  25, 220),
    2: ( 10, 128,  10),
    3: (200,  20,  20),
    4: ( 10,  10, 128),
    5: (128,  10,  10),
    6: (  0, 128, 128),
    7: (  0,   0,   0),
    8: (100, 100, 100),
}

STATUS_OK   = (200, 200, 200)
STATUS_WIN  = ( 80, 220,  80)
STATUS_LOSE = (220,  80,  80)

# ---------------------------------------------------------------------------
# Difficulty presets
# ---------------------------------------------------------------------------

# (name, rows, cols, mines, cell_px, toolbar_px)
DIFFICULTIES = {
    "1": ("Beginner",      9,  9, 10, 38, 56),
    "2": ("Intermediate", 16, 16, 40, 38, 56),
    "3": ("Expert",       16, 30, 99, 38, 56),
    "4": ("Phone",        15,  9, 20, 50, 50),  # 450×800 — exactly 9:16
}

# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_raised(surf, rect, color, border=3):
    """Draw a raised 3-D cell (unpressed)."""
    pygame.draw.rect(surf, color, rect)
    x, y, w, h = rect
    pygame.draw.polygon(surf, BORDER_LIGHT, [
        (x, y+h), (x, y), (x+w, y)
    ])
    pygame.draw.polygon(surf, BORDER_DARK, [
        (x, y+h), (x+w, y+h), (x+w, y)
    ])
    inner = (x+border, y+border, w-2*border, h-2*border)
    pygame.draw.rect(surf, color, inner)


def draw_sunken(surf, rect, color, border=2):
    """Draw a sunken 3-D cell (revealed)."""
    pygame.draw.rect(surf, color, rect)
    x, y, w, h = rect
    pygame.draw.polygon(surf, BORDER_DARK, [
        (x, y+h), (x, y), (x+w, y)
    ])
    pygame.draw.polygon(surf, BORDER_LIGHT, [
        (x, y+h), (x+w, y+h), (x+w, y)
    ])


def draw_flag(surf, cx, cy, size):
    """Draw a simple flag icon centred at (cx, cy)."""
    pole_x = cx - size // 6
    pole_top = cy - size // 2
    pole_bot = cy + size // 2
    # pole
    pygame.draw.line(surf, (30, 30, 30), (pole_x, pole_top), (pole_x, pole_bot), max(2, size//12))
    # flag
    pts = [
        (pole_x, pole_top),
        (pole_x + size // 2, pole_top + size // 4),
        (pole_x, pole_top + size // 2),
    ]
    pygame.draw.polygon(surf, (220, 30, 30), pts)


def draw_mine(surf, cx, cy, size, color=(30, 30, 30)):
    """Draw a simple mine icon."""
    r = max(4, size // 3)
    pygame.draw.circle(surf, color, (cx, cy), r)
    for angle_deg in range(0, 360, 45):
        import math
        rad = math.radians(angle_deg)
        x1 = cx + int((r - 1) * math.cos(rad))
        y1 = cy + int((r - 1) * math.sin(rad))
        x2 = cx + int((r + 4) * math.cos(rad))
        y2 = cy + int((r + 4) * math.sin(rad))
        pygame.draw.line(surf, color, (x1, y1), (x2, y2), max(1, size//16))


# ---------------------------------------------------------------------------
# Main game class
# ---------------------------------------------------------------------------

class MinesweeperApp:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Minesweeper + CVC5")
        self.guaranteed = False   # G key toggles guaranteed-solvable generation

        self._load_difficulty("1")
        pygame.display.flip()

    # ------------------------------------------------------------------

    def _load_difficulty(self, key: str):
        name, rows, cols, mines, cell_px, toolbar_px = DIFFICULTIES[key]
        self.diff_key    = key
        self.diff_name   = name
        self.rows        = rows
        self.cols        = cols
        self.num_mines   = mines
        self.cell_size   = cell_px
        self.toolbar_h   = toolbar_px
        self._new_game()

    def _new_game(self):
        self.hints: SolverResult | None = None
        self.elapsed         = 0.0
        self.start_time: float | None = None
        self.show_formula    = False
        self._formula_scroll = 0

        w = self.cols * self.cell_size
        h = self.rows * self.cell_size + self.toolbar_h
        self.screen = pygame.display.set_mode((w, h))

        if self.guaranteed:
            start = (self.rows // 2, self.cols // 2)
            self.board, _ = self._generate_with_live_splash(start)
            self.game        = GameState(self.board)
            self.first_click = False
            self.start_time  = None
            self.game.reveal(*start)
        else:
            self.board       = generate(self.rows, self.cols, self.num_mines)
            self.game        = GameState(self.board)
            self.first_click = True

    # ------------------------------------------------------------------

    def cell_rect(self, r: int, c: int) -> pygame.Rect:
        cs = self.cell_size
        return pygame.Rect(c * cs, self.toolbar_h + r * cs, cs, cs)

    def pos_to_cell(self, x: int, y: int) -> tuple[int, int] | None:
        if y < self.toolbar_h:
            return None
        c = x // self.cell_size
        r = (y - self.toolbar_h) // self.cell_size
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return r, c
        return None

    # ------------------------------------------------------------------

    def _draw_generating_splash(self, attempt: int, elapsed: float):
        w, h = self.screen.get_size()
        self.screen.fill((20, 20, 30))
        cx, cy = w // 2, h // 2

        title = render_text("Generating solvable board...", 20, (180, 220, 255), bold=True)
        self.screen.blit(title, (cx - title.get_width() // 2, cy - 44))

        sub = render_text("searching for a board requiring no guesses",
                          14, (100, 120, 140))
        self.screen.blit(sub, (cx - sub.get_width() // 2, cy - 16))

        stats = render_text(
            f"attempt {attempt}   {elapsed:.1f}s",
            18, (220, 200, 80), bold=True)
        self.screen.blit(stats, (cx - stats.get_width() // 2, cy + 14))

        pygame.display.flip()

    def _generate_with_live_splash(
            self, start: tuple[int, int]) -> tuple:
        """Run generate_solvable on a background thread; tick the splash at 10 Hz."""
        state = {'attempt': 1, 'board': None, 'error': None, 'done': False}

        def on_attempt(attempt, _elapsed):
            state['attempt'] = attempt + 1   # just finished attempt N, now trying N+1

        def worker():
            try:
                board, total = generate_solvable(
                    self.rows, self.cols, self.num_mines,
                    start=start, on_attempt=on_attempt)
                state['board'] = board
                state['attempt'] = total
            except Exception as exc:
                state['error'] = exc
            finally:
                state['done'] = True

        thread = threading.Thread(target=worker, daemon=True)
        t0 = time.monotonic()
        thread.start()

        clock = pygame.time.Clock()
        while not state['done']:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
            self._draw_generating_splash(state['attempt'], time.monotonic() - t0)
            clock.tick(10)

        thread.join()
        if state['error']:
            raise state['error']

        # draw one final frame showing the found attempt + time
        self._draw_generating_splash(state['attempt'], time.monotonic() - t0)
        pygame.display.flip()

        return state['board'], state['attempt']

    def _run_solver(self):
        self.hints = solve(self.game)

    def _apply_hints(self):
        if self.hints is None:
            self._run_solver()
        if self.hints is None:
            return
        for pos in self.hints.mines:
            if self.game.is_hidden(*pos):
                self.game.flag(*pos)
        for pos in self.hints.safe:
            if self.game.is_hidden(*pos):
                self.game.reveal(*pos)
        self.hints = None   # consumed

    # ------------------------------------------------------------------

    def _draw_toolbar(self):
        tw = self.cols * self.cell_size
        pygame.draw.rect(self.screen, TOOLBAR_BG, (0, 0, tw, self.toolbar_h))

        font_sz  = max(13, self.toolbar_h // 3)
        small_sz = max(11, self.toolbar_h // 4)
        y_main   = self.toolbar_h // 4
        y_hint   = self.toolbar_h * 2 // 3

        # mine counter
        remaining = self.num_mines - len(self.game.flagged_cells())
        surf = render_text(f"Mines: {remaining:3d}", font_sz, STATUS_OK, bold=True)
        self.screen.blit(surf, (12, y_main))

        # status / difficulty
        if self.game.won:
            status = "YOU WIN!  (R=new)"
            color  = STATUS_WIN
        elif self.game.game_over:
            status = "BOOM!  (R=new)"
            color  = STATUS_LOSE
        else:
            elapsed = self.elapsed
            if self.start_time and not self.game.game_over:
                elapsed = time.monotonic() - self.start_time
            status = f"{self.diff_name}  {int(elapsed):3d}s"
            color  = STATUS_OK
        surf = render_text(status, font_sz, color, bold=True)
        self.screen.blit(surf, (tw - surf.get_width() - 12, y_main))

        # hint key reminder + guaranteed indicator
        g_label = "[G: no-guess ON]" if self.guaranteed else "[G: no-guess off]"
        g_color = (80, 220, 80) if self.guaranteed else (120, 120, 120)
        hint = "S=hint  A=auto  F=formula  G=no-guess  R=new  1/2/3/4=diff"
        surf = render_text(hint, small_sz, (140, 140, 140))
        self.screen.blit(surf, (12, y_hint))
        g_surf = render_text(g_label, small_sz, g_color, bold=True)
        self.screen.blit(g_surf, (tw - g_surf.get_width() - 12, y_hint))

    def _draw_grid(self):
        hints_safe  = set(self.hints.safe)  if self.hints else set()
        hints_mines = set(self.hints.mines) if self.hints else set()

        for r in range(self.rows):
            for c in range(self.cols):
                rect = self.cell_rect(r, c)
                cx   = rect.centerx
                cy   = rect.centery
                pos  = (r, c)

                if self.game.is_revealed(r, c):
                    draw_sunken(self.screen, rect, CELL_REVEALED)
                    if self.board.is_mine(r, c):
                        pygame.draw.rect(self.screen, CELL_EXPLODED, rect)
                        draw_mine(self.screen, cx, cy, self.cell_size, (20, 20, 20))
                    else:
                        n = self.board.number(r, c)
                        if n > 0:
                            color = NUMBER_COLORS.get(n, (0, 0, 0))
                            num_sz = max(14, self.cell_size // 2)
                            surf = render_text(str(n), num_sz, color, bold=True)
                            self.screen.blit(
                                surf,
                                (cx - surf.get_width() // 2,
                                 cy - surf.get_height() // 2),
                            )
                elif self.game.is_flagged(r, c):
                    draw_raised(self.screen, rect, CELL_FLAG_BG)
                    draw_flag(self.screen, cx, cy, self.cell_size - 10)
                else:
                    # hidden — colour by hint
                    if pos in hints_safe:
                        color = CELL_HINT_SAFE
                    elif pos in hints_mines:
                        color = CELL_HINT_MINE
                    else:
                        color = CELL_HIDDEN
                    draw_raised(self.screen, rect, color)

        # if game over, reveal all un-flagged mines
        if self.game.game_over and not self.game.won:
            for pos in self.board.mines:
                r, c = pos
                if not self.game.is_flagged(r, c) and not self.game.is_revealed(r, c):
                    rect = self.cell_rect(r, c)
                    draw_raised(self.screen, rect, CELL_REVEALED)
                    draw_mine(self.screen, rect.centerx, rect.centery, self.cell_size)
            # wrong flags
            for r, c in self.game.flagged_cells():
                if not self.board.is_mine(r, c):
                    rect = self.cell_rect(r, c)
                    draw_raised(self.screen, rect, CELL_REVEALED)
                    draw_flag(self.screen, rect.centerx, rect.centery, self.cell_size - 10)
                    # cross out
                    pygame.draw.line(self.screen, (220, 0, 0),
                                     rect.topleft, rect.bottomright, 2)
                    pygame.draw.line(self.screen, (220, 0, 0),
                                     rect.topright, rect.bottomleft, 2)

    # ------------------------------------------------------------------
    # Formula overlay
    # ------------------------------------------------------------------

    def _build_formula_lines(self) -> list[tuple[str, tuple]]:
        """Return a list of (text, rgb_color) lines for the formula overlay."""
        WHITE  = (230, 230, 230)
        GREY   = (160, 160, 160)
        YELLOW = (240, 210,  60)
        CYAN   = ( 80, 210, 210)
        GREEN  = ( 80, 200,  80)
        RED    = (220,  80,  80)

        lines: list[tuple[str, tuple]] = []

        def sep(title=""):
            if title:
                bar = f"── {title} " + "─" * max(0, 50 - len(title))
            else:
                bar = "─" * 54
            lines.append((bar, GREY))

        # ── Variables ──────────────────────────────────────────────
        hidden = sorted(self.game.hidden_cells())
        sep("Variables  (x(r,c) ∈ {0,1},  1 = mine)")
        if not hidden:
            lines.append(("  (no hidden cells)", GREY))
        else:
            row_items: list[str] = []
            for r, c in hidden:
                row_items.append(f"x({r},{c})")
            line_buf = "  "
            for item in row_items:
                if len(line_buf) + len(item) + 2 > 56:
                    lines.append((line_buf.rstrip(", "), CYAN))
                    line_buf = "  "
                line_buf += item + ", "
            if line_buf.strip().rstrip(","):
                lines.append((line_buf.rstrip(", "), CYAN))

        # ── Constraints ────────────────────────────────────────────
        sep("Constraints  (φ)")
        constraints = self.game.constraint_cells()
        if not constraints:
            lines.append(("  (no constraints — reveal some cells first)", GREY))
        else:
            for (r, c), eff_n, nbrs in constraints:
                lhs = " + ".join(f"x({nr},{nc})" for nr, nc in sorted(nbrs))
                lines.append((f"  [{r},{c}]  {lhs}  =  {eff_n}", WHITE))

        # ── Proof queries ──────────────────────────────────────────
        sep("Proof Queries")
        lines.append(("  For each hidden cell, CVC5 runs two push/pop checks:", GREY))
        lines.append(("", GREY))
        lines.append(("  SAFE:  SAT( φ ∧ x(r,c) = 1 )  →  UNSAT", GREEN))
        lines.append(("         no valid board has (r,c) as a mine", GREY))
        lines.append(("         ⇒  φ  |-  x(r,c) = 0  (safe)", GREEN))
        lines.append(("", GREY))
        lines.append(("  MINE:  SAT( φ ∧ x(r,c) = 0 )  →  UNSAT", RED))
        lines.append(("         no valid board has (r,c) as safe", GREY))
        lines.append(("         ⇒  φ  |-  x(r,c) = 1  (mine)", RED))
        lines.append(("", GREY))

        # ── Per-cell query results ──────────────────────────────────
        sep("Query Results (last S press)")
        if self.hints is None:
            lines.append(("  (press S to run solver)", GREY))
        else:
            if not self.hints.safe and not self.hints.mines:
                lines.append(("  No cells could be determined.", GREY))
            for r, c in self.hints.safe:
                lines.append((
                    f"  SAT( φ ∧ x({r},{c}) = 1 )  →  UNSAT"
                    f"   ⇒  x({r},{c}) = 0  ✓ SAFE", GREEN))
            for r, c in self.hints.mines:
                lines.append((
                    f"  SAT( φ ∧ x({r},{c}) = 0 )  →  UNSAT"
                    f"   ⇒  x({r},{c}) = 1  ✗ MINE", RED))

        sep()
        lines.append((f"  {len(constraints)} constraint(s)  |  "
                      f"{len(hidden)} variable(s)  |  "
                      f"↑↓ or wheel to scroll  |  F to close",
                      YELLOW))
        return lines

    def _draw_formula_overlay(self):
        LINE_H  = 26
        FSIZE   = 16
        PAD     = 18
        TITLE_H = 38

        sw, sh = self.screen.get_size()
        ow = min(sw - 20, 900)
        oh = sh - 20
        ox = (sw - ow) // 2
        oy = 10

        # semi-transparent background
        panel = pygame.Surface((ow, oh), pygame.SRCALPHA)
        panel.fill((18, 18, 28, 220))
        pygame.draw.rect(panel, (90, 90, 140), (0, 0, ow, oh), 2)
        self.screen.blit(panel, (ox, oy))

        # title bar
        title_surf = render_text("SMT Formula  (QF_LIA)  --  F to close",
                                 17, (200, 200, 255), bold=True)
        self.screen.blit(title_surf, (ox + PAD, oy + 7))

        # scrollable content area
        content_y   = oy + TITLE_H
        content_h   = oh - TITLE_H - 4
        visible     = content_h // LINE_H
        lines       = self._build_formula_lines()
        max_scroll  = max(0, len(lines) - visible)
        self._formula_scroll = max(0, min(self._formula_scroll, max_scroll))

        # clip to panel
        clip = pygame.Rect(ox, content_y, ow, content_h)
        self.screen.set_clip(clip)

        for i, (text, color) in enumerate(lines[self._formula_scroll:
                                                  self._formula_scroll + visible + 1]):
            y = content_y + i * LINE_H
            surf = render_text(text, FSIZE, color)
            self.screen.blit(surf, (ox + PAD, y))

        self.screen.set_clip(None)

        # scrollbar
        if len(lines) > visible:
            bar_x    = ox + ow - 8
            bar_h    = content_h
            thumb_h  = max(20, int(bar_h * visible / len(lines)))
            thumb_y  = content_y + int(
                (bar_h - thumb_h) * self._formula_scroll / max_scroll
            ) if max_scroll else content_y
            pygame.draw.rect(self.screen, (50, 50, 80),
                             (bar_x, content_y, 6, bar_h))
            pygame.draw.rect(self.screen, (120, 120, 200),
                             (bar_x, thumb_y, 6, thumb_h), border_radius=3)

    # ------------------------------------------------------------------

    def run(self):
        clock = pygame.time.Clock()

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_g and not self.show_formula:
                        self.guaranteed = not self.guaranteed
                        self._new_game()
                    elif event.key == pygame.K_f:
                        self.show_formula = not self.show_formula
                    elif self.show_formula:
                        if event.key == pygame.K_UP:
                            self._formula_scroll = max(0, self._formula_scroll - 1)
                        elif event.key == pygame.K_DOWN:
                            self._formula_scroll += 1
                        elif event.key == pygame.K_PAGEUP:
                            self._formula_scroll = max(0, self._formula_scroll - 10)
                        elif event.key == pygame.K_PAGEDOWN:
                            self._formula_scroll += 10
                        elif event.key == pygame.K_ESCAPE:
                            self.show_formula = False
                    elif event.key == pygame.K_r:
                        self._new_game()
                    elif event.key == pygame.K_s and not self.game.game_over:
                        self._run_solver()
                    elif event.key == pygame.K_a and not self.game.game_over:
                        self._apply_hints()
                    elif event.unicode in DIFFICULTIES and not self.show_formula:
                        self._load_difficulty(event.unicode)

                elif event.type == pygame.MOUSEWHEEL and self.show_formula:
                    self._formula_scroll = max(0, self._formula_scroll - event.y)

                elif event.type == pygame.MOUSEBUTTONDOWN and not self.game.game_over:
                    cell = self.pos_to_cell(*event.pos)
                    if cell is None:
                        continue
                    r, c = cell

                    if event.button == 1:   # left click — reveal
                        if self.game.is_hidden(r, c):
                            if self.first_click:
                                # regenerate board so first click is always safe
                                self.board = generate(
                                    self.rows, self.cols, self.num_mines,
                                    safe_start=(r, c),
                                )
                                self.game  = GameState(self.board)
                                self.first_click = False
                                self.start_time = time.monotonic()
                            self.hints = None
                            self.game.reveal(r, c)

                    elif event.button == 3:  # right click — flag
                        if self.game.is_hidden(r, c):
                            self.game.flag(r, c)
                            self.hints = None
                        elif self.game.is_flagged(r, c):
                            self.game.unflag(r, c)
                            self.hints = None

            # update elapsed
            if self.start_time and not self.game.game_over:
                self.elapsed = time.monotonic() - self.start_time

            self.screen.fill(BG)
            self._draw_toolbar()
            self._draw_grid()
            if self.show_formula:
                self._draw_formula_overlay()
            pygame.display.flip()
            clock.tick(30)


if __name__ == "__main__":
    MinesweeperApp().run()
