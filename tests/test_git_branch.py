"""Tests for lisa.git.branch helper functions."""

from lisa.git.branch import find_next_suffix, get_base_slug


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
