"""Tests for lisa.init pure helper functions."""

from lisa.init import (
    _config_to_yaml,
    _ensure_min_fallback_tools,
    _gather_project_files,
    _print_config_preview,
    _read_file,
)


class TestEnsureMinFallbackTools:
    def test_empty(self):
        config = {"fallback_tools": ""}
        result = _ensure_min_fallback_tools(config)
        tools = result["fallback_tools"].split()
        assert "Read" in tools
        assert "Edit" in tools
        assert "Write" in tools
        assert "Grep" in tools
        assert "Glob" in tools
        assert "Skill" in tools
        assert "Bash(git:*)" in tools

    def test_preserves_extras(self):
        config = {"fallback_tools": "Read Edit Bash(cargo:*)"}
        result = _ensure_min_fallback_tools(config)
        tools = result["fallback_tools"].split()
        assert "Bash(cargo:*)" in tools
        assert "Read" in tools

    def test_no_dupes(self):
        config = {
            "fallback_tools": "Read Edit Write Grep Glob Skill Bash(git:*) Bash(cd:*) Bash(ls:*) Bash(mkdir:*) Bash(rm:*)"
        }
        result = _ensure_min_fallback_tools(config)
        tools = result["fallback_tools"].split()
        assert tools.count("Read") == 1

    def test_extras_sorted(self):
        config = {"fallback_tools": "Bash(pnpm:*) Bash(cargo:*)"}
        result = _ensure_min_fallback_tools(config)
        tools = result["fallback_tools"].split()
        # Extras should be sorted alphabetically after the min tools
        extras = [
            t
            for t in tools
            if t
            not in {
                "Read",
                "Edit",
                "Write",
                "Grep",
                "Glob",
                "Skill",
                "Bash(git:*)",
                "Bash(cd:*)",
                "Bash(ls:*)",
                "Bash(mkdir:*)",
                "Bash(rm:*)",
            }
        ]
        assert extras == sorted(extras)


class TestConfigToYaml:
    def test_basic(self):
        config = {"tests": [{"name": "pytest", "run": "pytest"}]}
        result = _config_to_yaml(config)
        assert "tests:" in result
        assert "pytest" in result

    def test_order_preserved(self):
        config = {"tests": [], "format": [], "fallback_tools": "Read"}
        result = _config_to_yaml(config)
        tests_pos = result.index("tests:")
        format_pos = result.index("format:")
        fallback_pos = result.index("fallback_tools:")
        assert tests_pos < format_pos < fallback_pos


class TestPrintConfigPreview:
    def test_outputs_yaml(self, capsys):
        config = {"tests": [{"name": "pytest", "run": "pytest"}]}
        _print_config_preview(config)
        out = capsys.readouterr().out
        assert "config.yaml" in out
        assert "pytest" in out


class TestReadFile:
    def test_reads(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = _read_file(str(f))
        assert result == "hello world"

    def test_truncates(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 10000)
        result = _read_file(str(f), max_chars=100)
        assert len(result) == 100

    def test_missing_file(self):
        result = _read_file("/nonexistent/path/file.txt")
        assert result is None


class TestGatherProjectFiles:
    def test_detects_files(self, tmp_path, monkeypatch):
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "README.md").write_text("# Hello")
        monkeypatch.chdir(tmp_path)
        result = _gather_project_files()
        assert "pyproject.toml" in result
        assert "README.md" in result

    def test_no_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = _gather_project_files()
        assert result == "none detected"
