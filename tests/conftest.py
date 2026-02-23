"""Shared test fixtures."""

import subprocess
import time

import pytest

from lisa.models.core import Assumption, ExplorationFindings
from lisa.models.state import RunConfig, WorkContext


@pytest.fixture
def sample_assumptions():
    return [
        Assumption(
            id="P.1", selected=True, statement="Use Redis for caching", rationale="Already in stack"
        ),
        Assumption(id="P.2", selected=False, statement="Add new dependency", rationale="Too heavy"),
        Assumption(id="1.1", selected=True, statement="Reuse auth module"),
        Assumption(
            id="2.1", selected=False, statement="Skip migration", rationale="Data loss risk"
        ),
    ]


@pytest.fixture
def sample_plan_steps():
    return [
        {"id": 1, "ticket": "ENG-71", "description": "Setup base config", "done": True},
        {
            "id": 2,
            "ticket": "ENG-72",
            "description": "Implement endpoint",
            "done": False,
            "files": [
                {"op": "create", "path": "src/api/handler.py", "template": "rest_handler"},
                {"op": "modify", "path": "src/api/routes.py", "detail": "add new route"},
            ],
        },
        {"id": 3, "ticket": "ENG-71", "description": "Write tests", "done": False},
    ]


@pytest.fixture
def sample_exploration():
    return ExplorationFindings(
        patterns=["REST handler pattern", "middleware chain"],
        relevant_modules=["src/api/", "src/auth/"],
        similar_implementations=[
            {"file": "src/api/users.py", "relevance": "similar CRUD handler"},
            {"file": "src/api/orders.py", "relevance": "same auth pattern"},
        ],
    )


@pytest.fixture
def reset_config_cache():
    import lisa.config.settings as settings

    settings._config = None
    settings._loaded_sources = []
    yield
    settings._config = None
    settings._loaded_sources = []


@pytest.fixture
def reset_token_tracker():
    from lisa.clients.claude import token_tracker
    from lisa.models.results import TokenUsage

    token_tracker.iteration = TokenUsage()
    token_tracker.total = TokenUsage()
    yield
    token_tracker.iteration = TokenUsage()
    token_tracker.total = TokenUsage()


@pytest.fixture
def mock_subprocess(mocker):
    """Mock subprocess.run returning success by default."""
    mock = mocker.patch("subprocess.run")
    mock.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
    return mock


@pytest.fixture
def sample_run_config():
    """Minimal RunConfig for tests."""
    return RunConfig(
        ticket_ids=["ENG-123"],
        max_iterations=10,
        effort="high",
        model="opus",
    )


@pytest.fixture
def sample_work_context(sample_run_config, sample_plan_steps):
    """WorkContext with sensible defaults for testing."""
    return WorkContext(
        ticket_id="ENG-123",
        title="Test ticket",
        description="Test description",
        issue_uuid="uuid-123",
        issue_url="https://linear.app/test/ENG-123",
        branch_name="eng-123-test",
        subtasks=[],
        plan_steps=sample_plan_steps,
        all_assumptions=[],
        assumptions=[],
        exploration=None,
        state_iteration=0,
        loop_iter=1,
        iter_start=time.time(),
        total_start=time.time(),
        current_step=None,
        step_desc=None,
        commit_ticket="ENG-123",
        work_result=None,
        last_test_error=None,
        last_review_issues=None,
        last_completion_issues=None,
        iter_state={},
        tests_passed=True,
        step_done=False,
        review_status="skipped",
        comment_id=None,
        log_entries=[],
        config=sample_run_config,
    )


@pytest.fixture
def reset_prompts_cache():
    import lisa.config.prompts as prompts

    prompts._prompts = None
    prompts._loaded_sources = []
    yield
    prompts._prompts = None
    prompts._loaded_sources = []


@pytest.fixture
def reset_schemas_cache():
    import lisa.config.schemas as schemas

    schemas._schemas = None
    yield
    schemas._schemas = None
