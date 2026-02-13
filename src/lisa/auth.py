"""OAuth PKCE browser login for Linear."""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

# Linear OAuth app - public PKCE client, no secret needed
CLIENT_ID = "6491511fa2aaf1debb7ed70af823f113"
AUTH_URL = "https://linear.app/oauth/authorize"
TOKEN_URL = "https://api.linear.app/oauth/token"
REDIRECT_PORT = 19284
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPES = "read,write"
CALLBACK_TIMEOUT = 120

TOKEN_DIR = Path.home() / ".config" / "lisa"
TOKEN_FILE = TOKEN_DIR / "auth.json"

# Refresh 5 minutes before expiry
REFRESH_BUFFER = 300


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code verifier and challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def _save_tokens(data: dict) -> None:
    """Save tokens to disk with restricted permissions."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, json.dumps(data).encode())
    finally:
        os.close(fd)


def _load_tokens() -> Optional[dict]:
    """Load tokens from disk."""
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _exchange_code(code: str, verifier: str) -> Optional[dict]:
    """Exchange authorization code for tokens."""
    body = urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier,
        }
    ).encode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(
            req, timeout=30
        ) as resp:  # nosemgrep: dynamic-urllib-use-detected
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"Token exchange failed: {e}")
        return None


def _refresh_access_token(refresh_token: str) -> Optional[dict]:
    """Refresh an expired access token."""
    body = urlencode(
        {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": refresh_token,
        }
    ).encode()

    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(
            req, timeout=30
        ) as resp:  # nosemgrep: dynamic-urllib-use-detected
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError):
        return None


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth callback code."""

    auth_code: Optional[str] = None
    error_msg: Optional[str] = None
    expected_state: Optional[str] = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_error(404)
            return

        params = parse_qs(parsed.query)

        if "error" in params:
            _CallbackHandler.error_msg = params["error"][0]
            self._respond("Login failed. You can close this tab.")
            return

        # Verify state to prevent CSRF
        state = params.get("state", [None])[0]
        if state != _CallbackHandler.expected_state:
            _CallbackHandler.error_msg = "State mismatch — possible CSRF"
            self._respond("Login failed. You can close this tab.")
            return

        code = params.get("code", [None])[0]
        if not code:
            _CallbackHandler.error_msg = "No authorization code received"
            self._respond("Login failed. You can close this tab.")
            return

        _CallbackHandler.auth_code = code
        self._respond("Login successful! You can close this tab.")

    def _respond(self, message: str) -> None:
        html = f"<html><body><h2>{message}</h2></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format: str, *args: object) -> None:
        pass  # Suppress request logging


def _run_callback_server(expected_state: str) -> Optional[str]:
    """Start local server, wait for callback, return auth code."""
    _CallbackHandler.auth_code = None
    _CallbackHandler.error_msg = None
    _CallbackHandler.expected_state = expected_state

    server = HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    server.timeout = CALLBACK_TIMEOUT

    server.handle_request()

    if _CallbackHandler.error_msg:
        print(f"OAuth error: {_CallbackHandler.error_msg}")
        return None

    return _CallbackHandler.auth_code


def run_login_flow() -> bool:
    """Run full PKCE OAuth flow. Returns True on success."""
    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(32)

    params = urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPES,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "prompt": "consent",
        }
    )
    auth_url = f"{AUTH_URL}?{params}"

    print("Opening browser for Linear login...")
    webbrowser.open(auth_url)
    print("Waiting for authorization (timeout: 120s)...")

    code = _run_callback_server(state)
    if not code:
        return False

    token_data = _exchange_code(code, verifier)
    if not token_data or "access_token" not in token_data:
        print("Failed to exchange code for token")
        return False

    _save_tokens(
        {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": time.time() + token_data.get("expires_in", 36000),
        }
    )
    return True


def get_token() -> Optional[str]:
    """Get a valid access token, refreshing if needed. Returns None if unavailable."""
    tokens = _load_tokens()
    if not tokens or not tokens.get("access_token"):
        return None

    expires_at = tokens.get("expires_at", 0)
    if time.time() < expires_at - REFRESH_BUFFER:
        return tokens["access_token"]

    # Token expired or expiring soon — try refresh
    refresh = tokens.get("refresh_token")
    if not refresh:
        return None

    new_data = _refresh_access_token(refresh)
    if not new_data or "access_token" not in new_data:
        print("Token expired and refresh failed. Run `lisa login` or set LINEAR_API_KEY.")
        return None

    _save_tokens(
        {
            "access_token": new_data["access_token"],
            "refresh_token": new_data.get("refresh_token", refresh),
            "expires_at": time.time() + new_data.get("expires_in", 36000),
        }
    )
    return new_data["access_token"]


def clear_tokens() -> None:
    """Delete stored auth tokens."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
