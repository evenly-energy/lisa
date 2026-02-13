"""Curses-based assumption editor."""

import curses
import textwrap
from typing import Optional

from lisa.models.core import Assumption, EditResult


def edit_assumptions_curses(
    assumptions: list[Assumption], context: str = ""
) -> Optional[EditResult]:
    """Interactive curses UI for editing assumption selections.

    Returns EditResult with assumptions and action ("continue" or "replan"), or None if user quits.

    Controls:
    - ↑/↓ or j/k: navigate
    - Space: toggle selection
    - e: edit rationale
    - Ctrl+R: replan with edited assumptions
    - Enter: confirm and continue
    - q: quit (returns None)
    """
    if not assumptions:
        return EditResult(assumptions=assumptions, action="continue")

    def _curses_main(stdscr) -> Optional[EditResult]:
        curses.curs_set(0)  # Hide cursor
        curses.start_color()
        curses.use_default_colors()

        # Define color pairs
        curses.init_pair(1, curses.COLOR_CYAN, -1)  # Header
        curses.init_pair(2, curses.COLOR_YELLOW, -1)  # Selected item
        curses.init_pair(3, curses.COLOR_GREEN, -1)  # Checkbox checked
        curses.init_pair(4, curses.COLOR_WHITE, -1)  # Normal text
        curses.init_pair(5, curses.COLOR_WHITE, -1)  # Gray fallback (dimmed via A_DIM)

        current = 0
        result = list(assumptions)  # Work with a copy

        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # Minimum size check
            if height < 8 or width < 40:
                stdscr.addstr(0, 0, "Terminal too small")
                stdscr.refresh()
                stdscr.getch()
                return None

            # Header (ASCII-safe box drawing)
            header = " Assumptions "
            stdscr.addstr(
                0, 0, "+-" + header + "-" * (width - len(header) - 4) + "+", curses.color_pair(1)
            )

            # Context line (if provided)
            if context:
                ctx_display = context[: width - 4]
                stdscr.addstr(1, 2, ctx_display, curses.color_pair(5) | curses.A_DIM)
                start_row = 3
            else:
                start_row = 2

            # Draw assumptions
            row = start_row
            for i, a in enumerate(result):
                if row >= height - 4:
                    break

                # Checkbox
                checkbox = "[x]" if a.selected else "[ ]"
                checkbox_color = curses.color_pair(3) if a.selected else curses.color_pair(4)

                # Highlight current item
                if i == current:
                    stdscr.addstr(row, 2, ">", curses.color_pair(2) | curses.A_BOLD)
                else:
                    stdscr.addstr(row, 2, " ")

                stdscr.addstr(row, 4, checkbox, checkbox_color)
                id_text = f"{a.id}. "
                stdscr.addstr(row, 8, id_text, curses.color_pair(4))

                # Statement (wrap across multiple lines)
                statement_col = 8 + len(id_text)
                max_line_len = width - statement_col - 2
                statement_lines = textwrap.wrap(a.statement, width=max_line_len) or [""]
                statement_color = (
                    curses.color_pair(2) | curses.A_BOLD if i == current else curses.color_pair(4)
                )
                for line in statement_lines:
                    if row >= height - 4:
                        break
                    stdscr.addstr(row, statement_col, line, statement_color)
                    row += 1

                # Rationale (wrap across multiple lines)
                if a.rationale and row < height - 4:
                    max_rationale_len = width - 14
                    rationale_lines = textwrap.wrap(a.rationale, width=max_rationale_len) or [""]
                    for line_idx, line in enumerate(rationale_lines):
                        if row >= height - 4:
                            break
                        prefix = "-> " if line_idx == 0 else "   "
                        stdscr.addstr(
                            row, 8, f"{prefix}{line}", curses.color_pair(5) | curses.A_DIM
                        )
                        row += 1

                row += 1  # Extra spacing between items

            # Footer (avoid last row - curses errors on last char)
            footer_row = height - 3
            stdscr.addstr(footer_row, 0, "+" + "-" * (width - 2) + "+", curses.color_pair(1))
            controls = "  j/k nav  SPACE toggle  e edit  ^R replan  ENTER confirm  q quit  "
            stdscr.addstr(
                footer_row + 1, 2, controls[: width - 4], curses.color_pair(5) | curses.A_DIM
            )

            stdscr.refresh()

            # Handle input
            key = stdscr.getch()

            if key in (ord("q"), ord("Q")):
                return None  # User quit
            elif key in (curses.KEY_UP, ord("k")):
                current = max(0, current - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                current = min(len(result) - 1, current + 1)
            elif key == ord(" "):
                # Toggle selection
                result[current] = Assumption(
                    id=result[current].id,
                    selected=not result[current].selected,
                    statement=result[current].statement,
                    rationale=result[current].rationale,
                )
            elif key == ord("e"):
                # Edit rationale - custom input with pre-fill and ESC support
                curses.curs_set(1)
                help_row = height - 3
                input_row = height - 2
                prompt = "Rationale: "
                buffer = list(result[current].rationale or "")
                max_input = width - len(prompt) - 2

                while True:
                    # Help line
                    stdscr.move(help_row, 0)
                    stdscr.clrtoeol()
                    stdscr.addstr(
                        help_row,
                        2,
                        "ENTER confirm  ESC cancel  ^U clear",
                        curses.color_pair(5) | curses.A_DIM,
                    )
                    # Input line
                    stdscr.move(input_row, 0)
                    stdscr.clrtoeol()
                    stdscr.addstr(input_row, 0, prompt, curses.color_pair(1))
                    display_text = "".join(buffer)[:max_input]
                    stdscr.addstr(input_row, len(prompt), display_text)
                    stdscr.refresh()

                    ch = stdscr.getch()
                    if ch == 27:  # ESC - cancel
                        break
                    elif ch in (curses.KEY_ENTER, 10, 13):  # Enter - confirm
                        result[current] = Assumption(
                            id=result[current].id,
                            selected=result[current].selected,
                            statement=result[current].statement,
                            rationale="".join(buffer).strip(),
                        )
                        break
                    elif ch == 21:  # Ctrl+U - clear
                        buffer.clear()
                    elif ch in (curses.KEY_BACKSPACE, 127, 8):  # Backspace
                        if buffer:
                            buffer.pop()
                    elif 32 <= ch <= 126:  # Printable ASCII
                        buffer.append(chr(ch))

                curses.curs_set(0)
            elif key == 18:  # Ctrl+R
                return EditResult(assumptions=result, action="replan")
            elif key in (curses.KEY_ENTER, 10, 13):
                return EditResult(assumptions=result, action="continue")

        return EditResult(assumptions=result, action="continue")

    return curses.wrapper(_curses_main)
