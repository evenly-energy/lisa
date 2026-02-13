"""Tests for lisa.config.utils."""

from lisa.config.utils import deep_merge, load_yaml


class TestDeepMerge:
    def test_empty_base(self):
        assert deep_merge({}, {"a": 1}) == {"a": 1}

    def test_empty_override(self):
        assert deep_merge({"a": 1}, {}) == {"a": 1}

    def test_both_empty(self):
        assert deep_merge({}, {}) == {}

    def test_scalar_replace(self):
        assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_list_replace(self):
        assert deep_merge({"a": [1, 2]}, {"a": [3]}) == {"a": [3]}

    def test_nested_dict_merge(self):
        base = {"a": {"b": 1, "c": 2}}
        override = {"a": {"c": 3, "d": 4}}
        assert deep_merge(base, override) == {"a": {"b": 1, "c": 3, "d": 4}}

    def test_three_level_deep(self):
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"d": 3, "e": 4}}}
        result = deep_merge(base, override)
        assert result == {"a": {"b": {"c": 1, "d": 3, "e": 4}}}

    def test_override_type_change(self):
        assert deep_merge({"a": {"b": 1}}, {"a": "string"}) == {"a": "string"}

    def test_base_not_mutated(self):
        base = {"a": {"b": 1}}
        deep_merge(base, {"a": {"c": 2}})
        assert base == {"a": {"b": 1}}

    def test_none_value(self):
        assert deep_merge({"a": 1}, {"a": None}) == {"a": None}

    def test_new_key(self):
        assert deep_merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}

    def test_nested_base_not_mutated(self):
        base = {"a": {"b": {"c": 1}}}
        deep_merge(base, {"a": {"b": {"d": 2}}})
        assert "d" not in base["a"]["b"]


class TestLoadYaml:
    def test_valid_yaml(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("key: value\nnested:\n  a: 1\n")
        result = load_yaml(f)
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_missing_file(self, tmp_path):
        assert load_yaml(tmp_path / "nope.yaml") is None

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.yaml"
        f.write_text("")
        assert load_yaml(f) is None

    def test_yaml_list_returns_none(self, tmp_path):
        f = tmp_path / "list.yaml"
        f.write_text("- a\n- b\n")
        assert load_yaml(f) is None

    def test_yaml_scalar_returns_none(self, tmp_path):
        f = tmp_path / "scalar.yaml"
        f.write_text("just a string\n")
        assert load_yaml(f) is None
