"""Tests for lisa.clients.linear."""

import json
import urllib.error

from lisa.clients.linear import (
    _get_auth_header,
    fetch_subtask_details,
    fetch_ticket,
    linear_api,
)


class TestGetAuthHeader:
    def test_env_var_takes_priority(self, monkeypatch, mocker):
        monkeypatch.setenv("LINEAR_API_KEY", "lin_api_key_123")
        mocker.patch("lisa.clients.linear.get_token", return_value="oauth-token")
        assert _get_auth_header() == "lin_api_key_123"

    def test_oauth_fallback(self, monkeypatch, mocker):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        mocker.patch("lisa.clients.linear.get_token", return_value="oauth-token")
        assert _get_auth_header() == "Bearer oauth-token"

    def test_no_auth(self, monkeypatch, mocker):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        mocker.patch("lisa.clients.linear.get_token", return_value=None)
        assert _get_auth_header() is None


class TestLinearApi:
    def test_no_auth(self, monkeypatch, mocker):
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        mocker.patch("lisa.clients.linear.get_token", return_value=None)
        assert linear_api("query {}") is None

    def test_success(self, monkeypatch, mocker):
        monkeypatch.setenv("LINEAR_API_KEY", "key")
        response_data = {"data": {"issue": {"id": "123"}}}
        mock_resp = mocker.MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch("lisa.clients.linear.urllib.request.urlopen", return_value=mock_resp)
        result = linear_api("query {}")
        assert result == {"issue": {"id": "123"}}

    def test_graphql_error(self, monkeypatch, mocker):
        monkeypatch.setenv("LINEAR_API_KEY", "key")
        response_data = {"errors": [{"message": "bad"}]}
        mock_resp = mocker.MagicMock()
        mock_resp.read.return_value = json.dumps(response_data).encode()
        mock_resp.__enter__ = mocker.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mocker.MagicMock(return_value=False)
        mocker.patch("lisa.clients.linear.urllib.request.urlopen", return_value=mock_resp)
        assert linear_api("query {}") is None

    def test_http_error(self, monkeypatch, mocker):
        monkeypatch.setenv("LINEAR_API_KEY", "key")
        mocker.patch(
            "lisa.clients.linear.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(None, 401, "Unauthorized", {}, None),
        )
        assert linear_api("query {}") is None

    def test_url_error(self, monkeypatch, mocker):
        monkeypatch.setenv("LINEAR_API_KEY", "key")
        mocker.patch(
            "lisa.clients.linear.urllib.request.urlopen",
            side_effect=urllib.error.URLError("timeout"),
        )
        assert linear_api("query {}") is None


class TestFetchTicket:
    def test_success(self, mocker):
        mocker.patch(
            "lisa.clients.linear.linear_api",
            return_value={
                "issue": {
                    "id": "uuid-1",
                    "identifier": "ENG-123",
                    "title": "Fix bug",
                    "description": "Details",
                    "url": "https://linear.app/ENG-123",
                    "project": {"id": "proj-1"},
                    "children": {
                        "nodes": [
                            {
                                "id": "child-uuid",
                                "identifier": "ENG-124",
                                "title": "Subtask",
                                "state": {"name": "Todo"},
                                "inverseRelations": {
                                    "nodes": [
                                        {"type": "blocks", "issue": {"identifier": "ENG-125"}}
                                    ]
                                },
                            }
                        ]
                    },
                }
            },
        )
        result = fetch_ticket("ENG-123")
        assert result["id"] == "ENG-123"
        assert result["uuid"] == "uuid-1"
        assert len(result["subtasks"]) == 1
        assert result["subtasks"][0]["blockedBy"] == ["ENG-125"]

    def test_not_found(self, mocker):
        mocker.patch("lisa.clients.linear.linear_api", return_value=None)
        assert fetch_ticket("NOPE") is None

    def test_no_subtasks(self, mocker):
        mocker.patch(
            "lisa.clients.linear.linear_api",
            return_value={
                "issue": {
                    "id": "uuid-1",
                    "identifier": "ENG-123",
                    "title": "Fix",
                    "description": "",
                    "url": "",
                    "project": {},
                    "children": {"nodes": []},
                }
            },
        )
        result = fetch_ticket("ENG-123")
        assert result["subtasks"] == []


class TestFetchSubtaskDetails:
    def test_success(self, mocker):
        mocker.patch(
            "lisa.clients.linear.linear_api",
            return_value={
                "issue": {
                    "identifier": "ENG-124",
                    "title": "Subtask",
                    "description": "Do things",
                }
            },
        )
        result = fetch_subtask_details("ENG-124")
        assert result["id"] == "ENG-124"
        assert result["title"] == "Subtask"

    def test_not_found(self, mocker):
        mocker.patch("lisa.clients.linear.linear_api", return_value=None)
        assert fetch_subtask_details("NOPE") is None
