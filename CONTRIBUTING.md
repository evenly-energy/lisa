# Contributing to Lisa

Thanks for your interest in contributing to Lisa! This guide will help you get started.

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/evenly-energy/lisa.git
   cd lisa
   ```

2. **Install dependencies**
   ```bash
   uv pip install -e ".[dev]"
   ```

3. **Install pre-commit hooks**
   ```bash
   pre-commit install
   ```

## Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov --cov-report=term-missing

# Run specific test file
pytest tests/test_config.py
```

## Code Quality

Before submitting a PR, ensure your code passes all quality checks:

```bash
# Linting
ruff check src/ tests/
ruff format src/ tests/

# Type checking
mypy src/

# All checks (run automatically via pre-commit)
pre-commit run --all-files
```

## Code Style

- **Line length**: 100 characters
- **Formatting**: Use `ruff format` (enforced via pre-commit)
- **Type hints**: Required for all new code
- **Docstrings**: Use for public functions and classes

## Pull Request Process

1. **Fork and branch**: Create a feature branch from `main`
2. **Write tests**: Add tests for new functionality
3. **Update docs**: Update README.md or CLAUDE.md if needed
4. **Run checks**: Ensure `mypy`, `ruff`, and `pytest` all pass
5. **Submit PR**: Provide a clear description of changes
6. **CI must pass**: All GitHub Actions checks must be green

## Architecture Overview

See [CLAUDE.md](CLAUDE.md) for detailed architecture documentation, including:
- State machine flow (`phases/work.py`)
- Config override system (`config/settings.py`, `config/prompts.py`)
- Structured output with JSON schemas (`schemas/default.yaml`)
- Git state persistence (`state/comment.py`, `state/git.py`)

## Adding New Features

When adding new phases or features:
1. Add prompts to `prompts/default.yaml` if Claude interaction needed
2. Add schemas to `schemas/default.yaml` for structured output
3. Update state models in `models/` if state changes needed
4. Add unit tests in `tests/`

## Questions?

- Open an [issue](https://github.com/evenly-energy/lisa/issues)
- Check existing issues and discussions first
