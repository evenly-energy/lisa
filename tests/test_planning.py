"""Tests for lisa.phases.planning.sort_by_dependencies."""

from lisa.phases.planning import sort_by_dependencies


class TestSortByDependencies:
    def test_empty(self):
        assert sort_by_dependencies([]) == []

    def test_no_deps(self):
        tasks = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        result = sort_by_dependencies(tasks)
        assert [t["id"] for t in result] == ["A", "B", "C"]

    def test_single_dep(self):
        tasks = [
            {"id": "B", "blockedBy": ["A"]},
            {"id": "A"},
        ]
        result = sort_by_dependencies(tasks)
        ids = [t["id"] for t in result]
        assert ids.index("A") < ids.index("B")

    def test_chain(self):
        tasks = [
            {"id": "C", "blockedBy": ["B"]},
            {"id": "B", "blockedBy": ["A"]},
            {"id": "A"},
        ]
        result = sort_by_dependencies(tasks)
        ids = [t["id"] for t in result]
        assert ids == ["A", "B", "C"]

    def test_diamond(self):
        tasks = [
            {"id": "D", "blockedBy": ["B", "C"]},
            {"id": "B", "blockedBy": ["A"]},
            {"id": "C", "blockedBy": ["A"]},
            {"id": "A"},
        ]
        result = sort_by_dependencies(tasks)
        ids = [t["id"] for t in result]
        assert ids.index("A") < ids.index("B")
        assert ids.index("A") < ids.index("C")
        assert ids.index("B") < ids.index("D")
        assert ids.index("C") < ids.index("D")

    def test_cycle_handled(self):
        tasks = [
            {"id": "A", "blockedBy": ["B"]},
            {"id": "B", "blockedBy": ["A"]},
        ]
        result = sort_by_dependencies(tasks)
        # Should not hang; all tasks returned
        assert len(result) == 2

    def test_external_dep_ignored(self):
        tasks = [
            {"id": "A", "blockedBy": ["EXTERNAL"]},
            {"id": "B"},
        ]
        result = sort_by_dependencies(tasks)
        # EXTERNAL not in subtask ids, so A is not blocked
        assert len(result) == 2

    def test_order_preserved_for_equal_priority(self):
        tasks = [{"id": "X"}, {"id": "Y"}, {"id": "Z"}]
        result = sort_by_dependencies(tasks)
        assert [t["id"] for t in result] == ["X", "Y", "Z"]

    def test_blocked_by_temp_field_cleaned(self):
        tasks = [{"id": "A"}, {"id": "B", "blockedBy": ["A"]}]
        result = sort_by_dependencies(tasks)
        for t in result:
            assert "_blocked_by" not in t
