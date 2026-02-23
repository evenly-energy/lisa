"""lisa init — interactive project setup for Lisa."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import yaml

from lisa.ui.output import BLUE, GRAY, GREEN, NC, YELLOW, error, log, success, warn

LISA_DIR = Path(".lisa")
CONFIG_FILE = LISA_DIR / "config.yaml"
SKILLS_DIR = Path(".claude") / "skills"


# --- Stack detection ---


def _file_exists(*paths: str) -> bool:
    return any(Path(p).exists() for p in paths)


def _read_file(path: str, max_chars: int = 5000) -> Optional[str]:
    try:
        return Path(path).read_text()[:max_chars]
    except (FileNotFoundError, OSError):
        return None


def _detect_package_manager() -> Optional[str]:
    """Detect JS/TS package manager from lock files."""
    if Path("pnpm-lock.yaml").exists():
        return "pnpm"
    if Path("yarn.lock").exists():
        return "yarn"
    if Path("bun.lockb").exists() or Path("bun.lock").exists():
        return "bun"
    if Path("package-lock.json").exists():
        return "npm"
    if Path("package.json").exists():
        return "npm"
    return None


def _read_package_json_scripts() -> dict:
    """Read scripts from package.json if present."""
    import json

    try:
        data = json.loads(Path("package.json").read_text())
        return data.get("scripts", {})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _detect_python_tools() -> dict:
    """Detect Python test/lint/format tools from pyproject.toml or config files."""
    tools = {"test": "pytest", "lint": None, "format": None}

    # Check for ruff
    if _file_exists("ruff.toml", ".ruff.toml"):
        tools["lint"] = "ruff"
        tools["format"] = "ruff"
    elif _file_exists("pyproject.toml"):
        content = _read_file("pyproject.toml") or ""
        if "[tool.ruff" in content:
            tools["lint"] = "ruff"
            tools["format"] = "ruff"
        if "[tool.black" in content:
            tools["format"] = "black"
        if "[tool.flake8" in content or "[tool.pylint" in content:
            tools["lint"] = tools.get("lint") or "flake8"

    # Check for mypy
    if _file_exists("mypy.ini", ".mypy.ini") or (
        _file_exists("pyproject.toml") and "[tool.mypy" in (_read_file("pyproject.toml") or "")
    ):
        tools["typecheck"] = "mypy"

    return tools


def detect_stack() -> dict:
    """Detect project stack from files. Returns config dict."""
    tests = []
    format_cmds = []
    fallback_tools = ["Read", "Edit", "Write", "Grep", "Glob", "Skill"]
    bash_tools = ["Bash(git:*)"]
    setup = []

    # --- Python ---
    if _file_exists("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"):
        py_tools = _detect_python_tools()

        # Package manager
        if _file_exists("pyproject.toml") and "uv" in (_read_file("pyproject.toml") or ""):
            bash_tools.append("Bash(uv:*)")
        bash_tools.append("Bash(pip:*)")
        bash_tools.append("Bash(python:*)")

        tests.append({"name": "Tests", "run": "pytest", "paths": ["**/*.py"]})

        if py_tools.get("lint") == "ruff":
            tests.append({"name": "Lint", "run": "ruff check .", "paths": ["**/*.py"]})
            format_cmds.append({"name": "Format", "run": "ruff format .", "paths": ["**/*.py"]})
        elif py_tools.get("lint"):
            tests.append({"name": "Lint", "run": f"{py_tools['lint']} .", "paths": ["**/*.py"]})

        if py_tools.get("typecheck"):
            tests.append({"name": "Type check", "run": "mypy .", "paths": ["**/*.py"]})

    # --- JavaScript/TypeScript ---
    pm = _detect_package_manager()
    if pm:
        scripts = _read_package_json_scripts()
        bash_tools.append(f"Bash({pm}:*)")
        if pm == "pnpm":
            bash_tools.append("Bash(npx:*)")
        elif pm == "npm":
            bash_tools.append("Bash(npx:*)")

        js_paths = ["**/*.{ts,tsx,js,jsx}"]

        if "test" in scripts:
            tests.append({"name": "Tests", "run": f"{pm} test", "paths": js_paths})
        if "lint" in scripts:
            tests.append({"name": "Lint", "run": f"{pm} run lint", "paths": js_paths})
        if "lint:check" in scripts:
            tests[-1]["run"] = f"{pm} run lint:check"
        if "format" in scripts or "format:check" in scripts:
            format_cmds.append({"name": "Format", "run": f"{pm} run format", "paths": js_paths})
        if "typecheck" in scripts or "type-check" in scripts:
            cmd = "typecheck" if "typecheck" in scripts else "type-check"
            tests.append({"name": "Type check", "run": f"{pm} run {cmd}", "paths": js_paths})

        setup.append({"name": "Install deps", "run": f"{pm} install"})

    # --- Kotlin/Java Gradle ---
    if _file_exists("build.gradle.kts", "build.gradle"):
        bash_tools.append("Bash(./gradlew:*)")

        tests.append(
            {
                "name": "Backend tests",
                "run": "./gradlew test",
                "paths": ["**/*.kt", "**/*.java"],
                "filter": '--tests "*{test}"',
            }
        )

        # Detect ktlint
        gradle_content = _read_file("build.gradle.kts") or _read_file("build.gradle") or ""
        if "ktlint" in gradle_content:
            tests.append({"name": "Lint", "run": "./gradlew ktlintCheck", "paths": ["**/*.kt"]})
            format_cmds.append(
                {"name": "Format", "run": "./gradlew ktlintFormat", "paths": ["**/*.kt"]}
            )
        if "detekt" in gradle_content:
            tests.append(
                {"name": "Static analysis", "run": "./gradlew detekt", "paths": ["**/*.kt"]}
            )

    # --- Maven ---
    if _file_exists("pom.xml") and not _file_exists("build.gradle.kts", "build.gradle"):
        bash_tools.append("Bash(mvn:*)")
        tests.append({"name": "Tests", "run": "mvn test", "paths": ["**/*.java", "**/*.kt"]})

    # --- Go ---
    if _file_exists("go.mod"):
        bash_tools.append("Bash(go:*)")
        tests.append({"name": "Tests", "run": "go test ./...", "paths": ["**/*.go"]})
        tests.append({"name": "Vet", "run": "go vet ./...", "paths": ["**/*.go"]})
        format_cmds.append({"name": "Format", "run": "gofmt -w .", "paths": ["**/*.go"]})

    # --- Rust ---
    if _file_exists("Cargo.toml"):
        bash_tools.append("Bash(cargo:*)")
        tests.append({"name": "Tests", "run": "cargo test", "paths": ["**/*.rs"]})
        tests.append({"name": "Clippy", "run": "cargo clippy", "paths": ["**/*.rs"]})
        format_cmds.append({"name": "Format", "run": "cargo fmt", "paths": ["**/*.rs"]})

    # Common bash tools
    bash_tools.extend(["Bash(cd:*)", "Bash(ls:*)", "Bash(mkdir:*)", "Bash(rm:*)"])

    # Build fallback_tools string
    ft = " ".join(fallback_tools) + "\n" + " ".join(bash_tools)

    config: dict = {}
    if tests:
        config["tests"] = tests
    if format_cmds:
        config["format"] = format_cmds
    if setup:
        config["setup"] = setup
    config["fallback_tools"] = ft

    return config


# --- Config preview and editing ---


def _config_to_yaml(config: dict) -> str:
    """Serialize config to YAML with readable formatting."""
    return yaml.dump(config, default_flow_style=False, sort_keys=False, width=120)


def _print_config_preview(config: dict) -> None:
    """Pretty-print config to terminal."""
    yaml_str = _config_to_yaml(config)
    print(f"\n{BLUE}{'─' * 50}{NC}")
    print(f"{GREEN}Generated .lisa/config.yaml:{NC}\n")
    for line in yaml_str.splitlines():
        if line.startswith("  ") or line.startswith("- "):
            print(f"  {line}")
        else:
            print(f"  {YELLOW}{line}{NC}")
    print(f"\n{BLUE}{'─' * 50}{NC}")


def _open_in_editor(content: str) -> Optional[str]:
    """Open content in $EDITOR. Returns edited content or None on failure."""
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vi"))

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    try:
        result = subprocess.run([editor, tmp_path])
        if result.returncode != 0:
            return None
        return Path(tmp_path).read_text()
    except (OSError, FileNotFoundError):
        error(f"Could not open editor '{editor}'. Set $EDITOR env var.")
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# --- Skill installation ---


REVIEW_TICKET_SKILL = """\
---
name: review-ticket
description: >-
  Review and validate a Linear ticket with its subtasks against the codebase.
  Identifies issues, suggests improvements, and outputs diff reports when making changes.
  Use for ticket refinement and validation.
user-invocable: true
allowed-tools: >-
  mcp__linear__get_issue, mcp__linear__list_issues, mcp__linear__update_issue,
  mcp__linear__create_issue, Task, Glob, Grep, Read, Skill
---

# Review Ticket

Deeply analyze a Linear ticket and its subtasks for correctness, completeness,
and alignment with the codebase.

## Triggers

Activate when user says:
- "review ENG-123"
- "validate ENG-45"
- "check ticket ENG-67"
- "analyze ENG-89 for issues"

## Process

### 1. Fetch Ticket Hierarchy

Get the target ticket with full details:
```
mcp__linear__get_issue(id, includeRelations: true)
```

Fetch all subtasks:
```
mcp__linear__list_issues(parentId: ticket.id)
```

For each subtask, get full details if description was truncated.

### 2. Explore Codebase (REQUIRED)

**You MUST use the Explore agent before producing any analysis.** This is not optional.

Use Task tool with `subagent_type: Explore` to understand:
- Existing patterns and conventions in the codebase
- Related entities, services, events
- Database migrations and schema
- API client methods and existing integrations

Focus exploration on ticket content:
- Event names: search for existing event classes and naming patterns
- Entity fields: find existing entity patterns and conventions
- API endpoints: explore controller patterns and routes
- Database schema: check migration patterns and naming

Example exploration prompt:
```
"Explore the codebase for patterns related to [ticket domain]. Find:
existing events, entities, services, and API patterns. Thoroughness: medium"
```

### 3. Review Documentation (when applicable)

If the repository has Claude Code skills (`.claude/skills/`) that document API
contracts, integration patterns, or domain conventions — load them using the
Skill tool before validating technical details.

This ensures ticket descriptions align with actual API contracts, field names,
and integration patterns documented in the project.

### 4. Validate Correctness

Check for:

**Naming Consistency**
- Event names match existing events in the codebase
- Entity naming follows project conventions
- Endpoint paths follow existing route patterns

**Technical Accuracy**
- API payloads match actual API contracts (check JSON casing, field names)
- Database fields align with entity conventions
- Referenced methods/classes actually exist in the codebase

**Scope Alignment**
- Subtasks cover all parent ticket DoD items
- No overlap or gaps between subtasks
- Clear boundaries between subtasks

**Architecture Fit**
- Follows module structure (public API vs internal)
- Event-driven patterns used correctly where applicable
- Proper separation of concerns

### 5. Output Analysis Report

Present findings in structured format:

```markdown
## Ticket Review: ENG-XXX - [Title]

### Sources Consulted
- **Codebase**: [areas explored, key files found]
- **Documentation**: [skills loaded, if any]

### Summary
[1-2 sentence overview]

### Subtasks
| ID | Title | Status |
|----|-------|--------|
| ENG-XX | ... | Backlog |

### Correctness
- [item] - [status] [details]

### Issues Found
1. **[Category]**: [description]
   - Current: [what ticket says]
   - Should be: [correct version]

### Potential Improvements
1. [suggestion]

### Missing Items
1. [gap identified]
```

### 6. Apply Changes (if requested)

When user approves changes:

1. Update tickets using `mcp__linear__update_issue`
2. Create new subtasks using `mcp__linear__create_issue`
3. Output diff report after all changes

## Diff Report Format

After making changes, output a diff view:

```markdown
## Changes Made

### ENG-XX (Title)
```diff
**Section:**
-Old text that was removed
+New text that was added

Unchanged context line
```

### NEW: ENG-YY (New Subtask Title)
Created subtask for [purpose]
```

## Tips

- Check for JSON casing mismatches (snake_case vs camelCase vs PascalCase)
- Verify event names against existing event classes in the codebase
- Cross-reference entity fields with existing entities
- Look for missing security/observability considerations
- Ensure idempotency is addressed for webhooks/events
"""

AVAILABLE_SKILLS = {
    "review-ticket": {
        "description": "Review and validate Linear tickets against the codebase before using Lisa",
        "content": REVIEW_TICKET_SKILL,
    },
}


def _install_skill(name: str, content: str) -> bool:
    """Write a skill file to .claude/skills/<name>/SKILL.md."""
    skill_dir = SKILLS_DIR / name
    skill_file = skill_dir / "SKILL.md"

    if skill_file.exists():
        warn(f"Skill '{name}' already exists at {skill_file}")
        try:
            answer = input("  Overwrite? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if answer not in ("y", "yes"):
            return False

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(content)
    return True


# --- Main init flow ---


def run_init() -> None:
    """Interactive project setup for Lisa."""
    print(f"\n{GREEN}Lisa Init{NC} — configure Lisa for this repository\n")

    # Check if already initialized
    if CONFIG_FILE.exists():
        warn(f"Found existing {CONFIG_FILE}")
        try:
            answer = (
                input("  Re-initialize? This will overwrite the config. [y/N] ").strip().lower()
            )
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if answer not in ("y", "yes"):
            log("Aborted.")
            sys.exit(0)

    # Read README for context
    readme = _read_file("README.md") or _read_file("readme.md")
    if readme:
        log(f"Read README.md ({len(readme)} chars) for project context")
    else:
        warn("No README.md found — detecting stack from project files only")

    # Detect stack
    log("Detecting project stack...")
    config = detect_stack()

    if not config.get("tests"):
        warn("Could not auto-detect test commands")
        log("You can add them manually after init")

    # Show preview
    _print_config_preview(config)

    # Ask user to confirm
    try:
        print(f"  {GRAY}(Y)es to write, (e)dit to open in $EDITOR, (n)o to cancel{NC}")
        answer = input(f"  Write to {CONFIG_FILE}? [Y/e/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)

    if answer in ("e", "edit"):
        yaml_str = _config_to_yaml(config)
        edited = _open_in_editor(yaml_str)
        if edited is None:
            error("Editor failed, aborting")
            sys.exit(1)
        # Validate the edited YAML
        try:
            config = yaml.safe_load(edited)
            if not isinstance(config, dict):
                raise ValueError("Config must be a YAML mapping")
        except (yaml.YAMLError, ValueError) as e:
            error(f"Invalid YAML: {e}")
            sys.exit(1)
        # Show updated preview
        _print_config_preview(config)
        try:
            confirm = input(f"  Write this config to {CONFIG_FILE}? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if confirm in ("n", "no"):
            log("Aborted.")
            sys.exit(0)
    elif answer in ("n", "no"):
        log("Aborted.")
        sys.exit(0)

    # Write config
    LISA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        f.write("# Lisa stack configuration\n")
        f.write("# See: https://github.com/evenly-energy/lisa#configuration\n")
        f.write(
            "# Override chain: bundled defaults < ~/.config/lisa/config.yaml < .lisa/config.yaml\n\n"
        )
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, width=120)
    success(f"Wrote {CONFIG_FILE}")

    # --- Skills ---
    print(f"\n{GREEN}Skills{NC} — optional Claude Code skills to enhance Lisa usage\n")

    for skill_name, skill_info in AVAILABLE_SKILLS.items():
        skill_file = SKILLS_DIR / skill_name / "SKILL.md"
        if skill_file.exists():
            log(f"  {skill_name}: already installed at {skill_file}")
            continue

        print(f"  {YELLOW}{skill_name}{NC}: {skill_info['description']}")
        try:
            answer = input(f"  Install {skill_name} skill? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if answer in ("n", "no"):
            continue

        if _install_skill(skill_name, skill_info["content"]):
            success(f"Installed {skill_name} skill at {SKILLS_DIR / skill_name / 'SKILL.md'}")

    # Done
    print(f"\n{GREEN}Done!{NC} Lisa is configured for this repository.")
    print(f"  Config: {CONFIG_FILE}")
    print(f"  Edit anytime: {GRAY}$EDITOR {CONFIG_FILE}{NC}")
    print(f"  Run: {GRAY}lisa ENG-123{NC}")
