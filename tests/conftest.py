"""Shared test fixtures."""

import pytest

from lisa.models.core import Assumption, ExplorationFindings


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
