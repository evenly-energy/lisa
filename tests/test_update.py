"""Tests for lisa.update."""

import json
import urllib.error

import lisa.update as update_mod
from lisa.update import (
    _fetch_latest_version,
    _load_cache,
    _save_cache,
    check_for_update,
    parse_version,
    run_upgrade,
)


class TestParseVersion:
    def test_simple(self):
        assert parse_version("0.4.1") == (0, 4, 1)

    def test_v_prefix(self):
        assert parse_version("v0.4.1") == (0, 4, 1)

    def test_two_parts(self):
        assert parse_version("1.0") == (1, 0)

    def test_dev(self):
        assert parse_version("dev") is None

    def test_dev_suffix(self):
        assert parse_version("0.3.1.dev11+gXXX") is None

    def test_plus_suffix(self):
        assert parse_version("0.4.1+local") is None

    def test_rc(self):
        assert parse_version("0.4.1rc1") is None

    def test_alpha(self):
        assert parse_version("1.0.0alpha") is None

    def test_beta(self):
        assert parse_version("1.0.0beta2") is None

    def test_empty(self):
        assert parse_version("") is None

    def test_invalid(self):
        assert parse_version("abc.def") is None

    def test_whitespace(self):
        assert parse_version("  v1.2.3  ") == (1, 2, 3)


class TestCacheLoadSave:
    def test_load_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(update_mod, "CACHE_FILE", tmp_path / "nope.json")
        assert _load_cache() is None

    def test_load_corrupt(self, tmp_path, monkeypatch):
        f = tmp_path / "bad.json"
        f.write_text("not json{{{")
        monkeypatch.setattr(update_mod, "CACHE_FILE", f)
        assert _load_cache() is None

    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(update_mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(update_mod, "CACHE_FILE", tmp_path / "update-check.json")
        _save_cache("1.2.3")
        cache = _load_cache()
        assert cache is not None
        assert cache["latest_version"] == "1.2.3"
        assert "last_check" in cache


class TestFetchLatestVersion:
    def test_success(self, monkeypatch):
        class FakeResp:
            def read(self):
                return json.dumps({"tag_name": "v0.5.0"}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())
        assert _fetch_latest_version() == "0.5.0"

    def test_network_error(self, monkeypatch):
        def fail(*a, **kw):
            raise urllib.error.URLError("timeout")

        monkeypatch.setattr(urllib.request, "urlopen", fail)
        assert _fetch_latest_version() is None

    def test_bad_json(self, monkeypatch):
        class FakeResp:
            def read(self):
                return b"not json"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())
        assert _fetch_latest_version() is None

    def test_missing_tag(self, monkeypatch):
        class FakeResp:
            def read(self):
                return json.dumps({}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())
        assert _fetch_latest_version() is None


class TestCheckForUpdate:
    def test_update_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(update_mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(update_mod, "CACHE_FILE", tmp_path / "update-check.json")

        class FakeResp:
            def read(self):
                return json.dumps({"tag_name": "v0.5.0"}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())
        assert check_for_update("0.4.0") == "0.5.0"

    def test_up_to_date(self, tmp_path, monkeypatch):
        monkeypatch.setattr(update_mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(update_mod, "CACHE_FILE", tmp_path / "update-check.json")

        class FakeResp:
            def read(self):
                return json.dumps({"tag_name": "v0.4.0"}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())
        assert check_for_update("0.4.0") is None

    def test_dev_version_skips(self):
        assert check_for_update("0.3.1.dev11+gXXX") is None

    def test_cache_hit(self, tmp_path, monkeypatch):
        import time

        monkeypatch.setattr(update_mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(update_mod, "CACHE_FILE", tmp_path / "update-check.json")

        # Write fresh cache
        (tmp_path / "update-check.json").write_text(
            json.dumps({"last_check": time.time(), "latest_version": "0.6.0"})
        )

        # urlopen should NOT be called — set it to fail
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda *a, **kw: (_ for _ in ()).throw(AssertionError("should not fetch")),
        )
        assert check_for_update("0.4.0") == "0.6.0"

    def test_cache_stale(self, tmp_path, monkeypatch):
        monkeypatch.setattr(update_mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(update_mod, "CACHE_FILE", tmp_path / "update-check.json")

        # Write stale cache (>24h old)
        (tmp_path / "update-check.json").write_text(
            json.dumps({"last_check": 0, "latest_version": "0.3.0"})
        )

        class FakeResp:
            def read(self):
                return json.dumps({"tag_name": "v0.7.0"}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())
        assert check_for_update("0.4.0") == "0.7.0"

    def test_network_failure_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(update_mod, "CACHE_DIR", tmp_path)
        monkeypatch.setattr(update_mod, "CACHE_FILE", tmp_path / "update-check.json")

        def fail(*a, **kw):
            raise urllib.error.URLError("no network")

        monkeypatch.setattr(urllib.request, "urlopen", fail)
        assert check_for_update("0.4.0") is None


class TestRunUpgrade:
    def _run(self, monkeypatch, **kwargs):
        called = {}
        monkeypatch.setattr(
            "lisa.update.subprocess.run",
            lambda cmd: (called.update(cmd=cmd), type("R", (), {"returncode": 0})())[1],
        )
        monkeypatch.setattr("lisa.update.sys.exit", lambda c: (_ for _ in ()).throw(SystemExit(c)))
        try:
            run_upgrade(**kwargs)
        except SystemExit:
            pass
        return called.get("cmd")

    def test_default_latest_release(self, monkeypatch):
        monkeypatch.setattr(update_mod, "_fetch_latest_version", lambda: "0.5.0")
        cmd = self._run(monkeypatch)
        assert cmd == [
            "uv",
            "tool",
            "install",
            "git+https://github.com/evenly-energy/lisa@v0.5.0",
            "--force",
        ]

    def test_main_flag(self, monkeypatch):
        cmd = self._run(monkeypatch, main=True)
        assert cmd == ["uv", "tool", "upgrade", "lisa"]

    def test_explicit_version(self, monkeypatch):
        cmd = self._run(monkeypatch, version="0.2.2")
        assert cmd == [
            "uv",
            "tool",
            "install",
            "git+https://github.com/evenly-energy/lisa@v0.2.2",
            "--force",
        ]

    def test_explicit_version_with_v_prefix(self, monkeypatch):
        cmd = self._run(monkeypatch, version="v0.2.2")
        assert cmd == [
            "uv",
            "tool",
            "install",
            "git+https://github.com/evenly-energy/lisa@v0.2.2",
            "--force",
        ]

    def test_default_fetch_fails(self, monkeypatch):
        monkeypatch.setattr(update_mod, "_fetch_latest_version", lambda: None)
        exit_code = None

        def fake_exit(c):
            nonlocal exit_code
            exit_code = c
            raise SystemExit(c)

        monkeypatch.setattr("lisa.update.sys.exit", fake_exit)
        try:
            run_upgrade()
        except SystemExit:
            pass
        assert exit_code == 1
