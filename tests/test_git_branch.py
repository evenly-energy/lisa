"""Tests for lisa.git.branch helper functions."""

import subprocess

from lisa.git.branch import (
    create_or_get_branch,
    determine_branch_name,
    find_next_suffix,
    generate_slug,
    get_base_slug,
    get_current_branch,
    get_default_branch,
    list_branches_matching,
)


class TestGetBaseSlug:
    def test_numeric_suffix_stripped(self):
        assert get_base_slug("eng-71-trade-mon-3", "eng-71") == "eng-71-trade-mon"

    def test_no_suffix(self):
        assert get_base_slug("eng-71-trade-mon", "eng-71") == "eng-71-trade-mon"

    def test_wrong_prefix(self):
        assert get_base_slug("other-branch", "eng-71") == "other-branch"

    def test_single_digit(self):
        assert get_base_slug("eng-71-foo-1", "eng-71") == "eng-71-foo"

    def test_multi_word(self):
        assert get_base_slug("eng-71-add-user-auth-5", "eng-71") == "eng-71-add-user-auth"


class TestFindNextSuffix:
    def test_no_existing(self):
        assert find_next_suffix([], "eng-71-foo") == 2

    def test_base_only(self):
        assert find_next_suffix(["eng-71-foo"], "eng-71-foo") == 2

    def test_one_increment(self):
        assert find_next_suffix(["eng-71-foo", "eng-71-foo-2"], "eng-71-foo") == 3

    def test_gap_in_sequence(self):
        assert find_next_suffix(["eng-71-foo", "eng-71-foo-2", "eng-71-foo-5"], "eng-71-foo") == 6

    def test_non_numeric_ignored(self):
        assert find_next_suffix(["eng-71-foo", "eng-71-foo-bar"], "eng-71-foo") == 2


class TestGetCurrentBranch:
    def test_returns_branch(self, mocker):
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="main\n", stderr=""),
        )
        assert get_current_branch() == "main"

    def test_detached_head(self, mocker):
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        assert get_current_branch() == ""

    def test_failure(self, mocker):
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="err"),
        )
        assert get_current_branch() == ""


class TestGetDefaultBranch:
    def test_from_origin_head(self, mocker):
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 0, stdout="refs/remotes/origin/main\n", stderr=""
            ),
        )
        assert get_default_branch() == "main"

    def test_fallback_to_main(self, mocker):
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 1, stdout="", stderr=""),  # symbolic-ref fails
                subprocess.CompletedProcess([], 0, stdout="hash\n", stderr=""),  # main exists
            ],
        )
        assert get_default_branch() == "main"

    def test_fallback_to_master(self, mocker):
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 1, stdout="", stderr=""),  # symbolic-ref fails
                subprocess.CompletedProcess([], 1, stdout="", stderr=""),  # main not found
                subprocess.CompletedProcess([], 0, stdout="hash\n", stderr=""),  # master exists
            ],
        )
        assert get_default_branch() == "master"

    def test_no_default(self, mocker):
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr=""),
        )
        assert get_default_branch() == ""


class TestListBranchesMatching:
    def test_returns_sorted(self, mocker):
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 0, stdout="  eng-71-foo\n* eng-71-bar\n", stderr=""
            ),
        )
        result = list_branches_matching("eng-71-*")
        assert result == ["eng-71-bar", "eng-71-foo"]

    def test_empty(self, mocker):
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        assert list_branches_matching("nope-*") == []

    def test_failure(self, mocker):
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="err"),
        )
        assert list_branches_matching("*") == []


class TestGenerateSlug:
    def test_generates_slug(self, mocker):
        import json

        mocker.patch(
            "lisa.git.branch.get_prompts",
            return_value={
                "slug": {"template": "slug {max_len} {title} {description}"},
            },
        )
        mocker.patch(
            "lisa.git.branch.get_schemas",
            return_value={
                "slug": {"type": "object"},
            },
        )
        mocker.patch("lisa.git.branch.claude", return_value=json.dumps({"slug": "add-auth"}))
        result = generate_slug("Add authentication", "Details", 20)
        assert result == "add-auth"

    def test_json_parse_fallback(self, mocker):
        mocker.patch(
            "lisa.git.branch.get_prompts",
            return_value={
                "slug": {"template": "slug {max_len} {title} {description}"},
            },
        )
        mocker.patch(
            "lisa.git.branch.get_schemas",
            return_value={
                "slug": {"type": "object"},
            },
        )
        mocker.patch("lisa.git.branch.claude", return_value="add-auth-handler")
        result = generate_slug("Add auth", "Desc", 20)
        assert result == "add-auth-handler"


class TestDetermineBranchName:
    def test_already_on_ticket_branch(self, mocker):
        mocker.patch("lisa.git.branch.get_current_branch", return_value="eng-1-foo")
        branch, exists = determine_branch_name("ENG-1", "Title", "Desc")
        assert branch == "eng-1-foo"
        assert exists is True

    def test_no_existing_branches(self, mocker):
        mocker.patch("lisa.git.branch.get_current_branch", return_value="main")
        mocker.patch("lisa.git.branch.list_branches_matching", return_value=[])
        mocker.patch("lisa.git.branch.generate_slug", return_value="add-auth")
        branch, exists = determine_branch_name("ENG-1", "Add auth", "Desc")
        assert branch == "eng-1-add-auth"
        assert exists is False

    def test_existing_branches_increments(self, mocker):
        mocker.patch("lisa.git.branch.get_current_branch", return_value="main")
        mocker.patch("lisa.git.branch.list_branches_matching", return_value=["eng-1-foo"])
        branch, exists = determine_branch_name("ENG-1", "Title", "Desc")
        assert branch == "eng-1-foo-2"
        assert exists is False


class TestCreateOrGetBranch:
    def test_already_on_branch(self, mocker):
        mocker.patch("lisa.git.branch.get_current_branch", return_value="eng-1-foo")
        result = create_or_get_branch("ENG-1", "Title", "Desc")
        assert result == "eng-1-foo"

    def test_creates_new_branch(self, mocker):
        mocker.patch("lisa.git.branch.get_current_branch", return_value="main")
        mocker.patch("lisa.git.branch.list_branches_matching", return_value=[])
        mocker.patch("lisa.git.branch.generate_slug", return_value="add-auth")
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        result = create_or_get_branch("ENG-1", "Add auth", "Desc")
        assert result == "eng-1-add-auth"

    def test_create_fails(self, mocker):
        mocker.patch("lisa.git.branch.get_current_branch", return_value="main")
        mocker.patch("lisa.git.branch.list_branches_matching", return_value=[])
        mocker.patch("lisa.git.branch.generate_slug", return_value="work")
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="err"),
        )
        assert create_or_get_branch("ENG-1", "Title", "Desc") is None

    def test_increments_existing(self, mocker):
        mocker.patch("lisa.git.branch.get_current_branch", return_value="main")
        mocker.patch("lisa.git.branch.list_branches_matching", return_value=["eng-1-foo"])
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        result = create_or_get_branch("ENG-1", "Title", "Desc")
        assert result == "eng-1-foo-2"

    def test_spice_mode(self, mocker):
        mocker.patch("lisa.git.branch.get_current_branch", return_value="main")
        mocker.patch("lisa.git.branch.list_branches_matching", return_value=[])
        mocker.patch("lisa.git.branch.generate_slug", return_value="work")
        mocker.patch(
            "lisa.git.branch.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, stdout="", stderr=""),
        )
        result = create_or_get_branch("ENG-1", "Title", "Desc", spice=True)
        assert result == "eng-1-work"
