"""Tests for lisa.git.commit helper functions."""

import subprocess

from lisa.git.commit import format_assumptions_trailer, get_changed_files
from lisa.models.core import Assumption


class TestFormatAssumptionsTrailer:
    def test_empty(self):
        assert format_assumptions_trailer([]) == ""

    def test_no_selected(self):
        assumptions = [Assumption(id="P.1", selected=False, statement="Skip it")]
        assert format_assumptions_trailer(assumptions) == ""

    def test_single_selected(self):
        assumptions = [Assumption(id="P.1", selected=True, statement="Use Redis")]
        assert format_assumptions_trailer(assumptions) == "Use Redis"

    def test_multiple_joined(self):
        assumptions = [
            Assumption(id="P.1", selected=True, statement="Use Redis"),
            Assumption(id="P.2", selected=True, statement="Add cache"),
        ]
        result = format_assumptions_trailer(assumptions)
        assert result == "Use Redis; Add cache"

    def test_truncation_at_50_chars(self):
        assumptions = [
            Assumption(id="P.1", selected=True, statement="A" * 60),
        ]
        result = format_assumptions_trailer(assumptions)
        assert len(result) == 50

    def test_mixed_selected_rejected(self):
        assumptions = [
            Assumption(id="P.1", selected=True, statement="Use Redis"),
            Assumption(id="P.2", selected=False, statement="Skip migration"),
            Assumption(id="P.3", selected=True, statement="Add tests"),
        ]
        result = format_assumptions_trailer(assumptions)
        assert "Use Redis" in result
        assert "Add tests" in result
        assert "Skip migration" not in result


class TestGetChangedFiles:
    def test_empty_status(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        assert get_changed_files() == []

    def test_modified_files(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout=" M src/foo.py\n M src/bar.py\n", stderr=""),
        )
        result = get_changed_files()
        assert "src/foo.py" in result
        assert "src/bar.py" in result

    def test_untracked_files(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="?? new_file.py\n", stderr=""),
        )
        result = get_changed_files()
        assert "new_file.py" in result

    def test_renamed_files(self, mocker):
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="R  old.py -> new.py\n", stderr=""),
        )
        result = get_changed_files()
        assert "new.py" in result

    def test_mixed_status(self, mocker):
        stdout = " M src/mod.py\n?? new.py\nA  added.py\n"
        mocker.patch(
            "lisa.git.commit.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout=stdout, stderr=""),
        )
        result = get_changed_files()
        assert len(result) == 3
