# Lisa - Looping Implementor Saving Assumptions

> `lisa` loves Ralph 💗

Autonomous Linear ticket implementation using Claude Code. Lisa advances the [Ralph loop](https://ghuntley.com/loop/) - reading your ticket, creating a plan, implementing step-by-step, testing, reviewing, and tracking every assumption in a Linear comment so you always know what decisions were made.

## Installation

```bash
# Install as CLI tool (recommended)
uv tool install git+https://github.com/evenly-energy/lisa

# Update to latest
uv tool upgrade lisa

# For development
git clone https://github.com/evenly-energy/lisa.git
cd lisa
uv pip install -e ".[dev]"
```

## Usage

```bash
# Basic usage
lisa ENG-123

# Build in temporary worktree (clean environment)
lisa ENG-123 -w

# Multiple tickets (processed serially)
lisa ENG-123 ENG-456

# Dry run - show plan without executing
lisa ENG-123 --dry-run

# Interactive mode - confirm assumptions
lisa ENG-123 -i

# Skip verification (faster, less safe)
lisa ENG-123 --skip-verify

# Review only - run final review on current changes
lisa ENG-123 --review-only

# Generate review guide for current branch
lisa ENG-123 --conclusion
```

## Environment Variables

- `LINEAR_API_KEY` (required) - Linear API key for ticket access

## Configuration

Create `.lisa/prompts.yaml` in your project to override defaults:

```yaml
config:
  # Path patterns for file category detection
  path_patterns:
    frontend: "frontend/**"
    backend: "**"

  # Extensions that identify frontend files
  frontend_extensions: [".ts", ".tsx", ".js", ".jsx"]

  # Tools allowed with --fallback-tools flag
  fallback_tools: >-
    Read Edit Write Grep Glob Skill
    Bash(git:*) Bash(./gradlew:*) Bash(pnpm:*)
    Bash(cd:*) Bash(ls:*) Bash(mkdir:*) Bash(rm:*)

  # Test retry optimization
  test_filter_templates:
    "./gradlew test": "./gradlew test {test_filters}"
  test_filter_format: '--tests "*{test_name}"'

# Test commands
test:
  commands:
    - name: "Backend tests"
      run: "./gradlew test"
      condition: "backend"
    - name: "Frontend tests"
      run: "npm test"
      condition: "frontend"
```

## How It Works

1. Fetches Linear ticket, subtasks, and blocking relations
2. Creates/checks out branch (reuses slug from existing branches)
3. Loads state from comment on ticket (🤖 lisa · {branch})
4. **Planning Phase**: Claude analyzes ticket and creates granular step checklist
5. Picks first incomplete step from plan
6. Runs Claude Code to work on that step
7. When step done: runs tests, code review, fix loop
8. Commits with: `feat(lisa): [ENG-456] step N - description`
9. Updates state comment on ticket
10. Repeats until max iterations reached

## Phases

1. **Planning** - Claude reads codebase, creates 3-8 granular steps
2. **Interactive** (optional, `-i`/`-I`) - Review/edit assumptions before proceeding
3. **Work** - Implement current step with Claude Code
4. **Test** - Run tests directly (no Claude, fast)
5. **Test-fix** - If tests fail, Claude fixes (max 3 attempts)
6. **Review** - Claude checks conventions, security, test quality
7. **Fix** - Claude fixes review issues, re-test after (max 3 attempts)
8. **Commit** - Save progress with structured commit message
9. **Final review** - When all steps done, comprehensive quality check

## Assumptions System

Lisa tracks decisions made during implementation:

- **Planning assumptions** (P.1, P.2, ...) - Decisions from planning phase
- **Work assumptions** (1.1, 1.2, 2.1, ...) - Decisions during each iteration

Assumptions are:
- Stored in Linear comment alongside plan progress
- Included in commit trailers (`Lisa-Assumptions:`)
- Editable via interactive mode (`-i` or `-I`)

### Interactive Mode

With `-i` or `-I`, a curses UI lets you review assumptions:
- **Space** - Toggle assumption selected/deselected
- **Ctrl+R** - Request replan with updated assumptions
- **Enter** - Continue with current assumptions

## State Tracking

Each branch has its own comment on the Linear ticket showing:
- Plan checklist with done/pending steps
- Current step indicator
- Iteration count and timestamps
- Assumptions made
- Recent log entries

State is resumable - re-running continues from where it left off.

## Backwards Compatibility

Lisa maintains backwards compatibility with tralph:
- Reads both `Lisa-*` and `Tralph-*` git trailers
- Reads both `🤖 **lisa**` and `🤖 **tralph**` comment headers
- Writes `Lisa-*` trailers and `lisa` headers for new state

## Options

```
-n, --max-iterations N    Max iterations (default: 30)
--max-turns N             Max turns per Claude session (default: 100)
-m, --model MODEL         Claude model (default: opus)
-p, --push                Push after each commit
--dry-run                 Show plan without executing
--skip-verify             Skip test and review phases
--skip-plan               Use subtasks directly
-i, --interactive         Confirm assumptions after planning
-I, --always-interactive  Confirm assumptions in all phases
--debug                   Log all JSON outputs
--review-only             Run final review and exit
--conclusion              Generate review guide and exit
-w, --worktree           Use temporary worktree
--yolo                   Skip all permission checks (unsafe)
--fallback-tools         Use explicit tool allowlist
```

## License

MIT
