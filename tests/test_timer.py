"""Tests for lisa.ui.timer."""

import time

import time_machine

from lisa.ui.timer import LiveTimer


class TestLiveTimer:
    def test_context_manager(self):
        t = LiveTimer("Test", time.time(), print_final=False)
        with t:
            pass
        # Should not raise

    def test_start_stop(self):
        t = LiveTimer("Test", time.time(), print_final=False)
        t.start()
        t.stop(print_final=False)
        assert t._thread is None

    def test_set_label(self):
        t = LiveTimer("Initial", time.time(), print_final=False)
        old_start = t.task_start
        time.sleep(0.01)
        t.set_label("New label")
        assert t.label == "New label"
        assert t.task_start > old_start

    @time_machine.travel("2026-01-01 12:00:00", tick=False)
    def test_get_elapsed(self):
        start = time.time()
        t = LiveTimer("Test", start, print_final=False)
        # time-machine frozen, so elapsed is 0s
        assert t.get_elapsed() == "0s"

    def test_print_final_true(self, capsys):
        t = LiveTimer("Test", time.time(), print_final=True)
        t.start()
        t.stop(print_final=True)
        out = capsys.readouterr().out
        assert "done in" in out

    def test_print_final_false(self, capsys):
        t = LiveTimer("Test", time.time(), print_final=False)
        t.start()
        t.stop(print_final=False)
        # Clear line only, no "done in"
        out = capsys.readouterr().out
        assert "done in" not in out

    def test_clear_line(self, capsys):
        t = LiveTimer("Test", time.time())
        t.clear_line()
        out = capsys.readouterr().out
        assert "\r\033[K" in out

    def test_stop_without_start(self):
        t = LiveTimer("Test", time.time(), print_final=False)
        t.stop(print_final=False)  # Should not raise

    def test_conclusion_in_output(self):
        t = LiveTimer("Working", time.time(), conclusion="step 1")
        assert t.conclusion == "step 1"

    def test_context_manager_print_final(self, capsys):
        with LiveTimer("Test", time.time(), print_final=True):
            pass
        out = capsys.readouterr().out
        assert "done in" in out

    def test_context_manager_no_print(self, capsys):
        with LiveTimer("Test", time.time(), print_final=False):
            pass
        out = capsys.readouterr().out
        assert "done in" not in out
