"""Tests for lisa.auth."""

import json
import urllib.error
from unittest.mock import MagicMock

import time_machine

from lisa.auth import (
    _CallbackHandler,
    _exchange_code,
    _generate_pkce,
    _load_tokens,
    _refresh_access_token,
    _run_callback_server,
    _save_tokens,
    clear_tokens,
    get_token,
    run_login_flow,
)


class TestGeneratePkce:
    def test_returns_verifier_and_challenge(self):
        verifier, challenge = _generate_pkce()
        assert len(verifier) > 40
        assert len(challenge) > 20

    def test_challenge_is_base64url(self):
        _, challenge = _generate_pkce()
        # base64url chars only, no padding
        assert "=" not in challenge
        assert all(c.isalnum() or c in "-_" for c in challenge)

    def test_unique_each_call(self):
        v1, _ = _generate_pkce()
        v2, _ = _generate_pkce()
        assert v1 != v2


class TestSaveLoadTokens:
    def test_roundtrip(self, tmp_path, monkeypatch):
        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_DIR", tmp_path)
        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "auth.json")

        data = {"access_token": "at", "refresh_token": "rt", "expires_at": 9999999999}
        _save_tokens(data)
        loaded = _load_tokens()
        assert loaded == data

    def test_load_missing_file(self, tmp_path, monkeypatch):
        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "nope.json")
        assert _load_tokens() is None

    def test_load_corrupt_json(self, tmp_path, monkeypatch):
        import lisa.auth as auth_mod

        token_file = tmp_path / "auth.json"
        token_file.write_text("not json{{")
        monkeypatch.setattr(auth_mod, "TOKEN_FILE", token_file)
        assert _load_tokens() is None

    def test_file_permissions(self, tmp_path, monkeypatch):
        import os

        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_DIR", tmp_path)
        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "auth.json")
        _save_tokens({"access_token": "secret"})
        mode = os.stat(tmp_path / "auth.json").st_mode & 0o777
        assert mode == 0o600


class TestGetToken:
    @time_machine.travel("2026-01-01 12:00:00")
    def test_valid_token(self, tmp_path, monkeypatch):
        import time

        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_DIR", tmp_path)
        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "auth.json")
        _save_tokens(
            {
                "access_token": "valid",
                "refresh_token": "rt",
                "expires_at": time.time() + 3600,
            }
        )
        assert get_token() == "valid"

    @time_machine.travel("2026-01-01 12:00:00")
    def test_expired_token_refreshes(self, tmp_path, monkeypatch, mocker):
        import time

        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_DIR", tmp_path)
        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "auth.json")
        _save_tokens(
            {
                "access_token": "old",
                "refresh_token": "rt",
                "expires_at": time.time() - 1,  # expired
            }
        )

        # Mock refresh
        refresh_data = {"access_token": "new", "refresh_token": "rt2", "expires_in": 36000}
        mock_resp = mocker.MagicMock()
        mock_resp.read.return_value = json.dumps(refresh_data).encode()
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch("lisa.auth.urllib.request.urlopen", return_value=mock_resp)

        assert get_token() == "new"

    @time_machine.travel("2026-01-01 12:00:00")
    def test_expiring_soon_refreshes(self, tmp_path, monkeypatch, mocker):
        import time

        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_DIR", tmp_path)
        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "auth.json")
        # Expires in 60s (within REFRESH_BUFFER of 300s)
        _save_tokens(
            {
                "access_token": "old",
                "refresh_token": "rt",
                "expires_at": time.time() + 60,
            }
        )

        refresh_data = {"access_token": "refreshed", "expires_in": 36000}
        mock_resp = mocker.MagicMock()
        mock_resp.read.return_value = json.dumps(refresh_data).encode()
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch("lisa.auth.urllib.request.urlopen", return_value=mock_resp)

        assert get_token() == "refreshed"

    def test_no_tokens(self, tmp_path, monkeypatch):
        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "nope.json")
        assert get_token() is None

    @time_machine.travel("2026-01-01 12:00:00")
    def test_refresh_fails(self, tmp_path, monkeypatch, mocker):
        import time

        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_DIR", tmp_path)
        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "auth.json")
        _save_tokens(
            {
                "access_token": "old",
                "refresh_token": "rt",
                "expires_at": time.time() - 1,
            }
        )
        mocker.patch(
            "lisa.auth.urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        )
        assert get_token() is None

    @time_machine.travel("2026-01-01 12:00:00")
    def test_no_refresh_token(self, tmp_path, monkeypatch):
        import time

        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_DIR", tmp_path)
        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "auth.json")
        _save_tokens(
            {
                "access_token": "old",
                "expires_at": time.time() - 1,
            }
        )
        assert get_token() is None


class TestExchangeCode:
    def test_success(self, mocker):
        token_data = {"access_token": "at", "refresh_token": "rt"}
        mock_resp = mocker.MagicMock()
        mock_resp.read.return_value = json.dumps(token_data).encode()
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch("lisa.auth.urllib.request.urlopen", return_value=mock_resp)
        result = _exchange_code("code123", "verifier123")
        assert result["access_token"] == "at"

    def test_failure(self, mocker):
        mocker.patch(
            "lisa.auth.urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        )
        assert _exchange_code("code", "verifier") is None


class TestRefreshAccessToken:
    def test_success(self, mocker):
        token_data = {"access_token": "new_at"}
        mock_resp = mocker.MagicMock()
        mock_resp.read.return_value = json.dumps(token_data).encode()
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch("lisa.auth.urllib.request.urlopen", return_value=mock_resp)
        result = _refresh_access_token("rt")
        assert result["access_token"] == "new_at"

    def test_failure(self, mocker):
        mocker.patch(
            "lisa.auth.urllib.request.urlopen",
            side_effect=urllib.error.URLError("err"),
        )
        assert _refresh_access_token("rt") is None


class TestClearTokens:
    def test_clears(self, tmp_path, monkeypatch):
        import lisa.auth as auth_mod

        token_file = tmp_path / "auth.json"
        token_file.write_text("{}")
        monkeypatch.setattr(auth_mod, "TOKEN_FILE", token_file)
        clear_tokens()
        assert not token_file.exists()

    def test_no_file(self, tmp_path, monkeypatch):
        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "nope.json")
        clear_tokens()  # Should not raise


class TestCallbackHandler:
    def _make_handler(self, path, expected_state=None):
        """Create a handler instance bypassing __init__."""
        handler = _CallbackHandler.__new__(_CallbackHandler)
        handler.path = path
        handler.wfile = MagicMock()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.send_error = MagicMock()
        # Reset class state
        _CallbackHandler.auth_code = None
        _CallbackHandler.error_msg = None
        _CallbackHandler.expected_state = expected_state
        return handler

    def test_success(self):
        handler = self._make_handler("/callback?code=abc123&state=s1", expected_state="s1")
        handler.do_GET()
        assert _CallbackHandler.auth_code == "abc123"
        assert _CallbackHandler.error_msg is None
        handler.send_response.assert_called_with(200)

    def test_error_param(self):
        handler = self._make_handler("/callback?error=access_denied", expected_state="s1")
        handler.do_GET()
        assert _CallbackHandler.error_msg == "access_denied"
        assert _CallbackHandler.auth_code is None

    def test_state_mismatch(self):
        handler = self._make_handler("/callback?code=abc&state=wrong", expected_state="expected")
        handler.do_GET()
        assert _CallbackHandler.error_msg is not None
        assert "State mismatch" in _CallbackHandler.error_msg

    def test_missing_code(self):
        handler = self._make_handler("/callback?state=s1", expected_state="s1")
        handler.do_GET()
        assert _CallbackHandler.error_msg is not None
        assert "No authorization code" in _CallbackHandler.error_msg

    def test_wrong_path(self):
        handler = self._make_handler("/other?code=abc", expected_state="s1")
        handler.do_GET()
        handler.send_error.assert_called_with(404)


class TestRunCallbackServer:
    def test_success(self, mocker):
        mock_server = MagicMock()

        def handle_request():
            _CallbackHandler.auth_code = "the_code"

        mock_server.handle_request = handle_request
        mocker.patch("lisa.auth.HTTPServer", return_value=mock_server)
        _CallbackHandler.auth_code = None
        _CallbackHandler.error_msg = None
        result = _run_callback_server("state123")
        assert result == "the_code"

    def test_error(self, mocker):
        mock_server = MagicMock()

        def handle_request():
            _CallbackHandler.error_msg = "denied"

        mock_server.handle_request = handle_request
        mocker.patch("lisa.auth.HTTPServer", return_value=mock_server)
        _CallbackHandler.auth_code = None
        _CallbackHandler.error_msg = None
        result = _run_callback_server("state123")
        assert result is None

    def test_no_callback(self, mocker):
        mock_server = MagicMock()
        mock_server.handle_request = MagicMock()
        mocker.patch("lisa.auth.HTTPServer", return_value=mock_server)
        _CallbackHandler.auth_code = None
        _CallbackHandler.error_msg = None
        result = _run_callback_server("state123")
        assert result is None


class TestRunLoginFlow:
    @time_machine.travel("2026-01-01 12:00:00")
    def test_success(self, tmp_path, monkeypatch, mocker):
        import lisa.auth as auth_mod

        monkeypatch.setattr(auth_mod, "TOKEN_DIR", tmp_path)
        monkeypatch.setattr(auth_mod, "TOKEN_FILE", tmp_path / "auth.json")
        mocker.patch("lisa.auth.webbrowser.open")
        mocker.patch("lisa.auth._run_callback_server", return_value="auth_code_123")
        mocker.patch(
            "lisa.auth._exchange_code",
            return_value={"access_token": "at", "refresh_token": "rt", "expires_in": 36000},
        )
        result = run_login_flow()
        assert result is True
        # Verify tokens were saved
        saved = json.loads((tmp_path / "auth.json").read_text())
        assert saved["access_token"] == "at"
        assert saved["refresh_token"] == "rt"

    def test_no_callback_code(self, mocker):
        mocker.patch("lisa.auth.webbrowser.open")
        mocker.patch("lisa.auth._run_callback_server", return_value=None)
        assert run_login_flow() is False

    def test_exchange_failure(self, mocker):
        mocker.patch("lisa.auth.webbrowser.open")
        mocker.patch("lisa.auth._run_callback_server", return_value="code")
        mocker.patch("lisa.auth._exchange_code", return_value=None)
        assert run_login_flow() is False

    def test_exchange_no_access_token(self, mocker):
        mocker.patch("lisa.auth.webbrowser.open")
        mocker.patch("lisa.auth._run_callback_server", return_value="code")
        mocker.patch("lisa.auth._exchange_code", return_value={"error": "bad"})
        assert run_login_flow() is False
