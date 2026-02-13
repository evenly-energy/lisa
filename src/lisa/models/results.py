"""Result models for test, review, and verification phases."""

from dataclasses import dataclass, field


@dataclass
class TestResult:
    """Result of running tests."""

    passed: bool
    errors: list[str] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)


@dataclass
class TestFailure:
    """Details of a test/lint failure for fix phase."""

    command_name: str
    output: str
    summary: str = ""
    failed_tests: list[str] = field(default_factory=list)  # Test class names for --tests filter


@dataclass
class ReviewResult:
    """Result of code review phase."""

    approved: bool
    issues: list[str] = field(default_factory=list)


@dataclass
class TokenUsage:
    """Token usage from a claude call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_creation_tokens + other.cache_creation_tokens,
            self.cost_usd + other.cost_usd,
        )


@dataclass
class VerifyResult:
    """Combined result of test/review/fix cycle."""

    passed: bool
    test_errors: list[str] = field(default_factory=list)
    review_issues: list[str] = field(default_factory=list)
    completion_issues: list[str] = field(default_factory=list)
    fix_attempts: int = 0
