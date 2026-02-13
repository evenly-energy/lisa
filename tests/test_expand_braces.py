"""Tests for brace expansion in path glob matching."""

from lisa.phases.verify import _expand_braces, should_run_command


class TestExpandBraces:
    def test_no_braces(self):
        assert _expand_braces("**/*.kt") == ["**/*.kt"]

    def test_single_alternative(self):
        assert _expand_braces("*.{ts}") == ["*.ts"]

    def test_two_alternatives(self):
        assert _expand_braces("*.{ts,tsx}") == ["*.ts", "*.tsx"]

    def test_many_alternatives(self):
        assert _expand_braces("frontend/**/*.{ts,tsx,js,jsx}") == [
            "frontend/**/*.ts",
            "frontend/**/*.tsx",
            "frontend/**/*.js",
            "frontend/**/*.jsx",
        ]

    def test_braces_in_middle(self):
        assert _expand_braces("src/{main,test}/**/*.kt") == [
            "src/main/**/*.kt",
            "src/test/**/*.kt",
        ]

    def test_empty_string(self):
        assert _expand_braces("") == [""]

    def test_only_first_brace_expanded(self):
        # Only one level of expansion — second brace stays literal
        result = _expand_braces("{a,b}.{c,d}")
        assert result == ["a.{c,d}", "b.{c,d}"]


class TestShouldRunCommand:
    def test_no_paths_always_runs(self):
        assert should_run_command({"name": "test"}, ["anything.py"])

    def test_matching_simple_glob(self):
        cmd = {"paths": ["**/*.kt"]}
        assert should_run_command(cmd, ["src/Foo.kt"])

    def test_no_match(self):
        cmd = {"paths": ["**/*.kt"]}
        assert not should_run_command(cmd, ["src/Foo.java"])

    def test_brace_expansion_match(self):
        cmd = {"paths": ["frontend/**/*.{ts,tsx,js,jsx}"]}
        assert should_run_command(cmd, ["frontend/src/app.tsx"])

    def test_brace_expansion_no_match(self):
        cmd = {"paths": ["frontend/**/*.{ts,tsx,js,jsx}"]}
        assert not should_run_command(cmd, ["frontend/package.json"])

    def test_multiple_patterns(self):
        cmd = {"paths": ["**/*.kt", "**/*.java"]}
        assert should_run_command(cmd, ["src/Main.java"])

    def test_no_changed_files(self):
        cmd = {"paths": ["**/*.kt"]}
        assert not should_run_command(cmd, [])
