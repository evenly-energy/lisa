# Lisa Development Guide

## What is Lisa?
Autonomous Linear ticket implementer. Reads ticket → plans steps → implements with Claude Code → tests → reviews → commits. Tracks all assumptions in Linear comments.

## Architecture

```
src/lisa/
├── cli.py           # Entry point
├── clients/         # claude.py (CLI wrapper), linear.py (GraphQL)
├── phases/          # Core loop: planning → work → verify → conclusion
├── models/          # PlanStep, Assumption, WorkState (FSM), WorkContext
├── state/           # Linear comment persistence
├── git/             # Branch/commit/worktree operations
├── config/          # prompts.py, settings.py, schemas.py, utils.py
├── defaults/        # Bundled config.yaml (stack defaults)
├── ui/              # Colored output, curses assumption editor
├── prompts/         # Default prompt templates (YAML)
└── schemas/         # JSON schemas for structured Claude output
```

## Key Files

- `cli.py` - Argument parsing, main() orchestration
- `phases/work.py` - State machine: SELECT_STEP → EXECUTE_WORK → VERIFY → COMMIT → SAVE_STATE
- `phases/verify.py` - Test/review/format/coverage phases
- `phases/planning.py` - Claude analyzes ticket → plan steps
- `clients/claude.py` - All Claude CLI interactions, token tracking
- `prompts/default.yaml` - Default prompts (override with .lisa/prompts.yaml)
- `defaults/config.yaml` - Default stack config (tests, format, coverage)
- `config/settings.py` - Stack config loading with layered overrides

## Patterns

### State Machine (work.py)
WorkState enum drives the loop. Each handler returns next state.
States: SELECT_STEP → EXECUTE_WORK → HANDLE_ASSUMPTIONS → CHECK_COMPLETION → VERIFY_STEP → COMMIT_CHANGES → SAVE_STATE → (loop or ALL_DONE)

### Assumptions
- Planning: P.1, P.2, ... (from planning phase)
- Work: 1.1, 1.2, 2.1, ... (iteration.index)
- Stored in Linear comment + git trailers

### Config Override
Two config files with same layered override chain (defaults < `~/.config/lisa/` < `.lisa/`):
- **prompts.yaml** — AI prompt templates (internal)
- **config.yaml** — Stack config: test/format/coverage commands, fallback tools (user-facing)

### Test Command Properties
Commands in the `tests` section support optional properties:
- **paths** (list[str]): Glob patterns for path filtering (e.g., `["**/*.kt"]`)
- **filter** (str): Format template for test retries (e.g., `'--tests "*{test}"'`)
- **preflight** (bool): Whether to run in preflight validation (default: `true`)
  - Set to `false` to skip expensive commands (e.g., integration tests) in preflight
  - Preflight only runs test commands; format commands run during commit phase

### Structured Output & Schemas
Lisa uses JSON schemas to get predictable Claude responses. Defined in `schemas/default.yaml`:

- **planning**: steps array, assumptions array, exploration findings (patterns, modules, similar implementations)
- **work**: step_done (int|null), blocked (string|null), assumptions array
- **test_extraction**: passed_count, failed_count, failed_tests array, extracted_output, summary
- **review**: approved bool, findings array [{category, status, detail}], summary
- **review_light**: approved bool, issue (string|null) - fast haiku review
- **conclusion_summary**: purpose, entry_point, flow, error_handling array, key_review_points array

Usage in `clients/claude.py`:
```python
output = work_claude(prompt, model, yolo, fallback_tools, effort, json_schema=schemas["work"])
result = json.loads(output)  # Guaranteed to match schema
```

Passed to Claude CLI via `--json-schema` flag.

## Commands

```bash
# Dev install
uv pip install -e ".[dev]"

# Run on ticket
lisa ENG-123

# Lint
ruff check src/
ruff format src/
```

## Environment
- `LINEAR_API_KEY` required
- Python 3.11+

## Testing Note
Lisa runs tests for *target projects* (via `verify.py`), not itself. Test commands come from `defaults/config.yaml` or project's `.lisa/config.yaml`.

## Adding New Phases
1. Create `phases/newphase.py` with `run_newphase()`
2. Add to `STATE_HANDLERS` dict in `work.py` if part of main loop
3. Or call directly from `cli.py` for standalone phases
4. Add prompts to `prompts/default.yaml` if Claude interaction needed
5. Add schemas to `schemas/default.yaml` for structured output

## Conventions
- All Claude calls via `clients/claude.py` (claude() or work_claude())
- Structured output via JSON schemas
- Backwards compat: reads both `Lisa-*` and `Tralph-*` git trailers
- No push by default (use --push flag)
- Haiku model: only use for data extraction from text, never for code analysis or review
- Version derived from git tags via `hatch-vcs` — just `git tag vX.Y.Z` to release
- The `/release` skill is pre-authorized to commit, tag, push, and create GitHub releases
