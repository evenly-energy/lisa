"""Core domain models."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class PlanStep:
    """A single step in the execution plan."""

    id: int
    description: str
    ticket: str = ""
    done: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "ticket": self.ticket,
            "done": self.done,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlanStep":
        return cls(
            id=d["id"],
            description=d["description"],
            ticket=d.get("ticket", ""),
            done=d.get("done", False),
        )


@dataclass
class Subtask:
    """A Linear subtask."""

    id: str
    uuid: str
    title: str
    state: str
    blocked_by: list[str] = field(default_factory=list)


@dataclass
class Ticket:
    """A Linear ticket with its subtasks."""

    id: str
    uuid: str
    title: str
    description: str
    project_id: str
    subtasks: list[Subtask] = field(default_factory=list)


@dataclass
class Assumption:
    """An assumption made during planning."""

    id: str  # "P.1", "1.1", "2.3", etc.
    selected: bool
    statement: str  # Neutral description: "Use Redis for caching"
    rationale: str = ""  # Why: "Already used by auth module"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "selected": self.selected,
            "statement": self.statement,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Assumption":
        # Handle legacy 'text' field
        statement = d.get("statement", d.get("text", ""))
        return cls(
            id=d["id"],
            selected=d["selected"],
            statement=statement,
            rationale=d.get("rationale", ""),
        )


@dataclass
class EditResult:
    """Result from edit_assumptions_curses."""

    assumptions: list[Assumption]
    action: Literal["continue", "replan"]


@dataclass
class ExplorationFindings:
    """Exploration findings from planning phase."""

    patterns: list[str] = field(default_factory=list)
    relevant_modules: list[str] = field(default_factory=list)
    similar_implementations: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "patterns": self.patterns,
            "relevant_modules": self.relevant_modules,
            "similar_implementations": self.similar_implementations,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ExplorationFindings":
        return cls(
            patterns=d.get("patterns", []),
            relevant_modules=d.get("relevant_modules", []),
            similar_implementations=d.get("similar_implementations", []),
        )
