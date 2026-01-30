"""Live updating timer for long-running operations."""

import threading
import time
from typing import Optional

from lisa.ui.output import BLUE, GRAY, NC, YELLOW, log
from lisa.utils.formatting import fmt_duration


class LiveTimer:
    """Display a live updating timer while a task runs. Can be used as context manager."""

    def __init__(
        self,
        label: str,
        total_start: float,
        print_final: bool = True,
        conclusion: str = "",
    ):
        self.label = label
        self.total_start = total_start
        self.print_final = print_final
        self.conclusion = conclusion
        self.task_start = time.time()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def __enter__(self) -> "LiveTimer":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop(print_final=self.print_final)

    def _run(self) -> None:
        while not self._stop.is_set():
            task_elapsed = fmt_duration(time.time() - self.task_start)
            total_elapsed = fmt_duration(time.time() - self.total_start)
            conclusion_str = f"  {GRAY}{self.conclusion}{NC}" if self.conclusion else ""
            print(
                f"\r\033[K{BLUE}[lisa]{NC} {self.label} {YELLOW}{task_elapsed}{NC} "
                f"(total: {total_elapsed}){conclusion_str}",
                end="",
                flush=True,
            )
            self._stop.wait(1.0)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def set_label(self, label: str) -> None:
        """Update the label and reset task timer."""
        self.label = label
        self.task_start = time.time()

    def clear_line(self) -> None:
        """Clear the timer line for other output."""
        print("\r\033[K", end="", flush=True)

    def get_elapsed(self) -> str:
        """Get formatted elapsed time since task start."""
        return fmt_duration(time.time() - self.task_start)

    def stop(self, print_final: bool = True) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        self._thread = None
        self.clear_line()
        if print_final:
            task_elapsed = fmt_duration(time.time() - self.task_start)
            total_elapsed = fmt_duration(time.time() - self.total_start)
            log(f"{self.label} done in {task_elapsed} (total: {total_elapsed})")
