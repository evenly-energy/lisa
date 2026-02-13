# Lisa - Looping Implementor Saving Assumptions

> Autonomous ticket implementation that never loses context.

What if your ticket backlog could implement itself?

Lisa is a harness that lets Claude Code work autonomously on Linear tickets without losing context. Point it at a ticket, and Lisa reads the requirements, breaks them into executable steps, implements each one with Claude Code, runs tests, performs code review, and commits—all while tracking every decision in Linear so humans stay in the loop.

No more context-switching between ticket, IDE, and terminal. No more "what was I doing?" after lunch. Lisa maintains state across sessions, resumes interrupted work, and produces a reviewer guide so your team can merge with confidence.

Lisa advances the [Ralph loop](https://ghuntley.com/loop/)—read ticket, plan, implement, test, review, commit—but fully automated.

## Prerequisites

System dependencies (not installed by pip):
- **Claude Code** - the `claude` CLI ([install from Anthropic](https://docs.anthropic.com/en/docs/claude-code))
- **git** - for branch/commit operations
- **Python 3.11+**

Python dependencies (auto-installed):
- `pyyaml>=6.0`

## Installation

```bash
# Install as CLI tool
uv tool install git+https://github.com/evenly-energy/lisa

# Update to latest
uv tool upgrade lisa

# For development
git clone https://github.com/evenly-energy/lisa.git
cd lisa
uv pip install -e ".[dev]"
```

Set your Linear API key:
```bash
export LINEAR_API_KEY="lin_api_..."
# Get from: Linear Settings → Security & access → Personal API keys
```

Run on a ticket:
```bash
lisa ENG-123

# Or in a clean worktree (recommended)
lisa ENG-123 -w
```

## How It Works

```
PRE-WORK           WORK LOOP              POST-WORK
─────────          ─────────              ─────────
Fetch ticket       Select step            Conclusion
Create branch  →   Execute work       →   Review guide
Plan steps         Verify (test/review)   Comment update
                   Commit progress
                   Save state
                   (repeat)
```

## PRE-WORK Phase

### Ticket Fetch
Pulls the Linear ticket with description, subtasks, and blocking relations.

### Branch Management
Creates or reuses a branch named `{ticket-id}-{slug}`. If you're already on a ticket branch, Lisa stays there. Otherwise creates a new incremental branch (e.g., `eng-123-foo-2`).

### State Restoration
Resumes from the Lisa comment on the ticket (`🤖 lisa · {branch}`). Tracks iteration count, completed steps, and assumptions.

### Planning
Claude explores the codebase and generates 5-20 granular steps with:
- File operations (create/modify/delete) per step
- Similar implementations to use as templates
- Planning assumptions (P.1, P.2, ...)

Subtasks are topologically sorted by blocking relations before planning.

### Interactive Mode (`-i`)
Review and edit assumptions before work begins. Curses UI with:
- **Space** - Toggle assumption selected/deselected
- **Ctrl+R** - Request replan with updated assumptions
- **Enter** - Continue with current assumptions

## WORK Loop

State machine: `SELECT_STEP → EXECUTE_WORK → HANDLE_ASSUMPTIONS → CHECK_COMPLETION → VERIFY_STEP → COMMIT_CHANGES → SAVE_STATE`

### Execute
Claude Code implements the current step with context from:
- Plan and exploration findings
- Planning assumptions to follow
- Prior iteration history
- Any test/review failures to fix

### Verify
Test → test-fix → review → fix cycle (max 2 attempts each):
1. **Test**: runs configured test commands directly
2. **Test-fix**: if tests fail, Claude fixes and re-tests
3. **Review**: Claude checks conventions, security, test quality
4. **Fix**: Claude fixes review issues, re-tests after

### Commit
Structured message with git trailers:
```
feat(lisa): [ENG-123] step 3: add webhook handler

Lisa-Iteration: 5
Lisa-Step: 3
Lisa-Assumptions: P.1, 5.1, 5.2
```

### Save State
Updates the Linear comment with:
- Plan checklist (done/pending steps)
- Current step indicator
- Iteration count and timestamps
- Assumptions made
- Recent log entries

## POST-WORK Phase

### Conclusion
When all steps complete, Lisa generates a **reviewer guide**:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 Review Guide: ENG-123 - Add webhook notifications

Purpose
  Enables real-time notifications when devices change status
  by sending HTTP webhooks to configured endpoints.

Entry Point
  POST /api/webhooks → WebhookController.register()

Flow
  1. Request validated in WebhookController.register()
  2. WebhookService.create() persists to DB
  3. DeviceService emits events → WebhookDispatcher listens
  4. Dispatcher sends HTTP POST to registered URLs

Error Handling
  1. WebhookService.create(): duplicate URL → 409 Conflict
  2. WebhookDispatcher.send(): connection timeout → queued for retry

Key Review Points
  1. ⚠ WebhookDispatcher.send()
     Async HTTP call with 5s timeout
     Risk: blocking if executor pool exhausted

Test Coverage
  ✓ Happy path: webhook creation and dispatch
  ✗ Malformed JSON handling
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

The review guide is saved to the Linear comment and printed to terminal.

## Structured Output & Schemas

Lisa uses JSON schemas to get predictable Claude responses. Schemas are defined in `schemas/default.yaml`:

- **planning**: steps, assumptions, exploration findings
- **work**: step_done signal, blocked reason, work assumptions
- **test_extraction**: failed test names, error summary
- **review**: approved/rejected with findings
- **conclusion_summary**: purpose, flow, error handling, review points

Passed to Claude CLI via `--json-schema` for validated output.

## Worktrees & Serial Ticket Work

### Worktrees (`-w`)
Creates an isolated worktree in `/tmp/lisa/{session}` for clean builds. Auto-cleaned on exit.

### Multiple Tickets
```bash
lisa ENG-123 ENG-456 ENG-789
```
Processed serially. Each ticket gets its own branch and state.

## Configuration

> Note: Lisa was built for the evenly-platform stack (Kotlin/Gradle backend, TypeScript frontend) and defaults reflect that. Any stack works with config overrides.

Lisa uses two config files, each with three layers deep-merged (later wins):

| Layer | Config (stack) | Prompts (AI) |
|-------|------|-------|
| Defaults | bundled `defaults/config.yaml` | bundled `prompts/default.yaml` |
| Global | `~/.config/lisa/config.yaml` | `~/.config/lisa/prompts.yaml` |
| Project | `.lisa/config.yaml` | `.lisa/prompts.yaml` |

Deep merge means you only need to specify the keys you want to change — everything else keeps its default value. Dicts merge recursively, lists and scalars replace.

### Stack config (`config.yaml`)

The stack config controls which commands Lisa runs for testing, formatting, and coverage. Each command can have `paths` globs — the command only runs if a changed file matches. Omit `paths` to always run.

```yaml
# .lisa/config.yaml — only specify what you want to override

tests:
  - name: Backend tests
    run: ./gradlew test
    paths: ["**/*.kt", "**/*.java"]
    filter: '--tests "*{test}"'
  - name: Frontend tests
    run: npm test
    paths: ["frontend/**"]

format:
  - name: Kotlin format
    run: ./gradlew ktlintFormat
    paths: ["**/*.kt"]

coverage:
  run: ./gradlew koverVerify
  paths: ["**/*.kt"]

fallback_tools: >-
  Read Edit Write Grep Glob Skill
  Bash(git:*) Bash(npm:*)
```

#### Examples

**Python project:**
```yaml
tests:
  - name: pytest
    run: pytest
    paths: ["**/*.py"]

format:
  - name: ruff
    run: ruff format .
    paths: ["**/*.py"]

coverage:
  run: pytest --cov --cov-fail-under=80
  paths: ["**/*.py"]
```

**Node.js project:**
```yaml
tests:
  - name: vitest
    run: npm test

format:
  - name: prettier
    run: npx prettier --write .

coverage: {}
```

Active overrides are logged at startup.

## CLI Reference

```
lisa TICKET_ID [TICKET_ID ...] [options]

Options:
  -n, --max-iterations N    Max iterations (default: 30)
  --max-turns N             Max turns per Claude session (default: 100)
  -m, --model MODEL         Claude model (default: opus)
  -p, --push                Push after each commit
  --dry-run                 Show plan without executing
  --skip-verify             Skip test and review phases
  --skip-plan               Use subtasks directly as steps
  -i, --interactive         Confirm assumptions after planning
  -I, --always-interactive  Confirm assumptions in all phases
  --debug                   Log all JSON outputs to .lisa/debug.log
  --review-only             Run final review on current changes
  --conclusion              Generate review guide and exit
  -w, --worktree            Use temporary worktree
  --yolo                    Skip all permission checks (unsafe)
  --fallback-tools          Use explicit tool allowlist
  -v, --version             Show version
```

## Assumptions System

Lisa tracks decisions made during implementation:

- **Planning assumptions** (P.1, P.2, ...) - Decisions from planning phase
- **Work assumptions** (1.1, 1.2, 2.1, ...) - Decisions during each iteration

Assumptions are:
- Stored in Linear comment alongside plan progress
- Included in commit trailers (`Lisa-Assumptions:`)
- Editable via interactive mode (`-i` or `-I`)

## State Tracking

Each branch has its own comment on the Linear ticket showing:
- Plan checklist with done/pending steps
- Current step indicator
- Iteration count and timestamps
- Assumptions made
- Recent log entries

State is resumable—re-running continues from where it left off.

## Development

```bash
# Dev install
uv pip install -e ".[dev]"

# Lint
ruff check src/
ruff format src/
```

See `CLAUDE.md` for architecture patterns and implementation details.

## License

MIT
