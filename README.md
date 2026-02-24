# Lisa - Looping Implementor Saving Assumptions

[![CI](https://github.com/evenly-energy/lisa/actions/workflows/ci.yml/badge.svg)](https://github.com/evenly-energy/lisa/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/evenly-energy/lisa/main/coverage-badge.json)](https://github.com/evenly-energy/lisa/blob/main/coverage-badge.json)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

> Autonomous ticket implementation that never loses context.

Lisa is a harness that lets Claude Code work autonomously on Linear tickets. It advances the [Ralph loop](https://ghuntley.com/loop/) — read ticket, plan, implement, test, review, commit — as a state machine that resumes across sessions. Plans and progress live in Linear comments and git trailers, not markdown files polluting your repo.

Point it at a ticket and it will:
- **Fetch** the ticket, subtasks, and blocking relations
- **Branch** — create or resume a ticket branch (optionally in a worktree)
- **Preflight** — run tests/linting to verify clean state (optional, `-c`)
- **Plan** — Claude explores the codebase and creates granular steps
- **Loop** (up to 30 iterations by default):
  - **Execute** — implement with Claude Code
  - **Verify** — run tests, fix failures, code review, fix issues
  - **Commit** — structured message with assumptions in git trailers
  - **Save state** — update Linear comment with plan progress
- **Final review** — comprehensive code review of all changes, fix loop until approved
- **Conclude** — generate a reviewer guide: entry points, flow, error handling, and key review points posted to Linear

## Install

Prerequisites: [Claude Code](https://docs.anthropic.com/en/docs/claude-code), git, Python 3.11+

```bash
uv tool install git+https://github.com/evenly-energy/lisa
```

Authenticate with Linear:
```bash
lisa login                              # browser-based OAuth (recommended)
# or: export LINEAR_API_KEY="lin_api_..."
```

## Usage

```bash
lisa ENG-123                             # implement a ticket
lisa ENG-123 -w                          # in an isolated worktree
lisa ENG-123 -wc                         # worktree + preflight checks
lisa ENG-123 ENG-456 -ws --push          # stacked PRs via git-spice
lisa ENG-123 --dry-run                   # preview plan only
lisa ENG-123 --review-only               # review current changes
lisa ENG-123 --conclusion                # generate reviewer guide
```

## Subcommands

| Command | Description |
|---------|-------------|
| `lisa init` | Set up `.lisa/` config for this project |
| `lisa login` | Authenticate with Linear (OAuth) |
| `lisa logout` | Clear stored Linear tokens |
| `lisa upgrade` | Upgrade to latest release |
| `lisa upgrade --main` | Upgrade to latest main snapshot |
| `lisa upgrade <version>` | Pin to specific version (e.g. `0.4.1`) |

## Configuration

Run `lisa init` to generate `.lisa/config.yaml` for your project.

```yaml
# .lisa/config.yaml
tests:
  - name: Backend tests
    run: ./gradlew test
    paths: ["**/*.kt", "**/*.java"]
    filter: '--tests "*{test}"'
  - name: Frontend tests
    run: npm test
    paths: ["frontend/**"]
    preflight: false

format:
  - name: Kotlin format
    run: ./gradlew ktlintFormat
    paths: ["**/*.kt"]

coverage:
  run: ./gradlew koverVerify
  paths: ["**/*.kt"]

setup:
  run: cd frontend && npm install
```

## CLI Flags

```
lisa TICKET_ID [TICKET_ID ...] [options]
```

| Flag | Description |
|------|-------------|
| `-n, --max-iterations N` | Max iterations (default: 30) |
| `-m, --model MODEL` | Claude model (default: opus) |
| `-p, --push` | Push after each commit |
| `-w, --worktree` | Run in temporary worktree |
| `-c, --preflight` | Run tests/linting before starting |
| `-s, --spice` | Use git-spice for stacked branches |
| `-i, --interactive` | Confirm assumptions after planning |
| `-I, --always-interactive` | Confirm assumptions in all phases |
| `--dry-run` | Show plan without executing |
| `--skip-verify` | Skip test and review phases |
| `--skip-plan` | Use subtasks directly as steps |
| `--effort LEVEL` | Effort level cap: low, medium, high (default: high) |
| `--review-only` | Run final review on current changes |
| `--conclusion` | Generate review guide and exit |
| `--yolo` | Skip all permission checks (unsafe) |
| `--fallback-tools` | Use explicit tool allowlist |
| `--debug` | Log JSON outputs to `.lisa/debug.log` |
| `--verbose` | Show raw API responses |
| `-v, --version` | Show version |

## Hook Suppression

Lisa sets `LISA_SESSION=1` in the environment of its Claude subprocess calls. Use this in your `~/.claude/settings.json` hooks to distinguish autonomous Lisa runs from interactive sessions.

## Development

```bash
uv pip install -e ".[dev]"
ruff check src/ && ruff format src/
```

See `CLAUDE.md` for architecture and implementation details.

## License

MIT
