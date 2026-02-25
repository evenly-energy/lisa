"""lisa init — interactive project setup for Lisa."""

import importlib.resources
import json
import os
import shlex
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

_MIN_FALLBACK_TOOLS = {
    "Read",
    "Edit",
    "Write",
    "Grep",
    "Glob",
    "Skill",
    "Bash(git:*)",
    "Bash(cd:*)",
    "Bash(ls:*)",
    "Bash(mkdir:*)",
    "Bash(rm:*)",
}

_MIN_FALLBACK_TOOLS_ORDERED = [
    "Read",
    "Edit",
    "Write",
    "Grep",
    "Glob",
    "Skill",
    "Bash(git:*)",
    "Bash(cd:*)",
    "Bash(ls:*)",
    "Bash(mkdir:*)",
    "Bash(rm:*)",
]


def _ensure_min_fallback_tools(config: dict) -> dict:
    """Merge minimum required tools into fallback_tools, preserving extras."""
    current = set(config.get("fallback_tools", "").split())
    extras = sorted(current - _MIN_FALLBACK_TOOLS)
    config["fallback_tools"] = " ".join(_MIN_FALLBACK_TOOLS_ORDERED + extras)
    return config


# --- Linear auth + team detection ---


def _try_linear_auth(yes: bool = False) -> bool:
    """Try to authenticate with Linear. Returns True if authenticated."""
    if os.environ.get("LINEAR_API_KEY"):
        return True

    from lisa.auth import get_token, run_login_flow

    if get_token():
        return True

    log("No Linear authentication found.")
    log("Options: set LINEAR_API_KEY env var or login via browser.")

    if yes:
        log("  Attempting browser login (--yes)")
        if run_login_flow():
            success("Logged in to Linear successfully.")
            return True
        else:
            warn("Login failed, continuing without Linear.")
            return False

    try:
        answer = input("  Login via browser now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if answer in ("", "y", "yes"):
        if run_login_flow():
            success("Logged in to Linear successfully.")
            return True
        else:
            warn("Login failed, continuing without Linear.")
            return False
    return False


def _detect_ticket_codes(linear_authenticated: bool, yes: bool = False) -> list:
    """Detect ticket codes from Linear teams, or ask user manually."""
    if linear_authenticated:
        from lisa.clients.linear import fetch_teams

        teams = fetch_teams()
        if teams is None:
            warn("Could not fetch teams from Linear.")
        elif not teams:
            warn("No teams found in your Linear workspace.")
        elif len(teams) == 1:
            code = teams[0]["key"]
            log(f"Found Linear team: {teams[0]['name']} ({code})")
            return [code]
        else:
            # Multiple teams — ask which to use
            log("Found Linear teams:")
            for i, t in enumerate(teams, 1):
                print(f"  {i}. {t['name']} ({t['key']})")

            if yes:
                log("  Selecting all teams (--yes)")
                return [t["key"] for t in teams]

            try:
                answer = input(
                    "  Use which teams? (comma-separated numbers, or Enter for all): "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return [t["key"] for t in teams]

            if not answer:
                return [t["key"] for t in teams]

            selected = []
            for part in answer.split(","):
                try:
                    idx = int(part.strip()) - 1
                    if 0 <= idx < len(teams):
                        selected.append(teams[idx]["key"])
                except ValueError:
                    pass
            if not selected:
                warn("Could not parse selection, using all teams")
            return selected or [t["key"] for t in teams]

    # No auth or fetch failed — ask manually
    if yes:
        log('  Using default ticket prefix "ENG" (--yes)')
        return ["ENG"]

    try:
        codes_input = input("  Enter ticket prefixes (e.g. ENG,FE,BE): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ["ENG"]
    if codes_input:
        return [c.strip().upper() for c in codes_input.split(",") if c.strip()]
    return ["ENG"]


# --- Helpers ---


def _read_file(path: str, max_chars: int = 5000) -> Optional[str]:
    try:
        return Path(path).read_text()[:max_chars]
    except (FileNotFoundError, OSError):
        return None


# --- Claude-based config detection ---


def _gather_project_files() -> str:
    """List project files that exist, for context in Claude prompt."""
    files_to_check = [
        "README.md",
        "readme.md",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "package.json",
        "tsconfig.json",
        "build.gradle.kts",
        "build.gradle",
        "settings.gradle.kts",
        "pom.xml",
        "Cargo.toml",
        "go.mod",
        "Makefile",
        "Dockerfile",
        "docker-compose.yml",
        ".eslintrc.json",
        ".eslintrc.js",
        "eslint.config.js",
        "ruff.toml",
        ".ruff.toml",
        "pnpm-lock.yaml",
        "yarn.lock",
        "package-lock.json",
        "bun.lockb",
        "bun.lock",
    ]
    found = [f for f in files_to_check if Path(f).exists()]
    return ", ".join(found) if found else "none detected"


def _claude_detect_config() -> Optional[dict]:
    """Use Claude to generate config.yaml by exploring the project."""
    from lisa.clients.claude import claude
    from lisa.config.schemas import get_schemas

    schemas = get_schemas()
    schema = schemas.get("init_config")
    if not schema:
        error("Missing 'init_config' schema — lisa installation may be corrupted")
        return None

    found_files = _gather_project_files()
    readme = _read_file("README.md", max_chars=3000) or _read_file("readme.md", max_chars=3000)
    readme_section = f"\n\n## README.md (excerpt)\n{readme}" if readme else ""

    prompt = f"""Analyze this project and generate a Lisa CI config.

## Project files found
{found_files}
{readme_section}

## What to generate
A config with these sections:

### tests
Array of test/lint/typecheck commands. Each entry:
- name: human label (e.g. "Tests", "Lint", "Type check")
- run: shell command
- paths: glob patterns for files that trigger this (e.g. ["**/*.py"])
- filter: (optional) template for running specific failed tests, use {{test}} placeholder
  e.g. '-k "{{test}}"' for pytest, '--tests "*{{test}}"' for gradle
- preflight: (optional) set false to skip slow commands in preflight

### format
Array of auto-format commands. Each entry: name, run, paths.

### coverage
(optional) Single object with: run (shell command), paths (glob patterns).
Only include if the project has a coverage tool configured (e.g. kover, coverage.py, c8/istanbul).

### setup
Array of dependency install commands (only if needed, e.g. for JS projects).
Each entry: name, run.

### fallback_tools
Space-separated string of Claude Code tools. Always start with:
  Read Edit Write Grep Glob Skill Bash(git:*) Bash(cd:*) Bash(ls:*) Bash(mkdir:*) Bash(rm:*)
Then add build tool permissions like Bash(./gradlew:*), Bash(pnpm:*), Bash(cargo:*), etc.

## Rules
- Read the actual project files to detect tools (don't guess)
- Use the correct package manager based on lock files
- Only include commands for tools that are actually configured
- For monorepos, detect sub-projects
- Keep commands concise and correct
- tests array should not be empty — at minimum detect a test runner"""

    try:
        result = claude(
            prompt,
            model="sonnet",
            allowed_tools="Read Glob Grep",
            effort="low",
            json_schema=schema,
        )
    except FileNotFoundError:
        error("Claude CLI not found — install from https://docs.anthropic.com/claude-code")
        return None
    except Exception as e:
        warn(f"Claude config detection failed: {e}")
        return None

    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        warn("Claude returned invalid JSON")
        return None

    if not isinstance(data, dict):
        warn(f"Claude returned unexpected type: {type(data).__name__}")
        return None
    if not data.get("tests"):
        warn("Claude returned config with no test commands")
        return None
    return data


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
        result = subprocess.run(shlex.split(editor) + [tmp_path])
        if result.returncode != 0:
            error(f"Editor '{editor}' exited with code {result.returncode}")
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


# --- Skill template loading ---


def _load_skill_template(name: str) -> Optional[str]:
    """Load a bundled skill template from defaults/skills/."""
    try:
        files = importlib.resources.files("lisa")
        path = files / "defaults" / "skills" / f"{name}.md"
        return path.read_text()
    except (FileNotFoundError, TypeError):
        dev_path = Path(__file__).parent / "defaults" / "skills" / f"{name}.md"
        if dev_path.exists():
            return dev_path.read_text()
        return None


def _render_skill(template: str, ticket_codes: list) -> str:
    """Replace {ticket_prefix} placeholders with actual ticket codes."""
    primary = ticket_codes[0] if ticket_codes else "ENG"
    return template.replace("{ticket_prefix}", primary)


def _get_available_skills(ticket_codes: list) -> dict:
    """Build available skills dict with rendered templates."""
    skills = {}
    template = _load_skill_template("review-ticket")
    if template:
        skills["review-ticket"] = {
            "description": "Review and validate Linear tickets against the codebase before using Lisa",
            "content": _render_skill(template, ticket_codes),
        }
    return skills


def _install_skill(name: str, content: str, yes: bool = False) -> bool:
    """Write a skill file to .claude/skills/<name>/SKILL.md."""
    skill_dir = SKILLS_DIR / name
    skill_file = skill_dir / "SKILL.md"

    if skill_file.exists():
        if yes:
            log(f"  Overwriting existing skill '{name}' (--yes)")
        else:
            warn(f"Skill '{name}' already exists at {skill_file}")
            try:
                answer = input("  Overwrite? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return False
            if answer not in ("y", "yes"):
                return False

    try:
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(content)
    except OSError as e:
        error(f"Failed to write skill '{name}': {e}")
        return False
    return True


# --- How-to guide ---


def _print_howto(ticket_codes: list) -> None:
    """Print getting-started guide after init."""
    prefix = ticket_codes[0] if ticket_codes else "ENG"
    ex = f"{prefix}-123"

    print(f"\n{GREEN}{'=' * 50}{NC}")
    print(f"{GREEN}Lisa is ready!{NC}\n")
    print(f"  Config:  {GRAY}{CONFIG_FILE}{NC}")
    print(f"  Edit:    {GRAY}$EDITOR {CONFIG_FILE}{NC}")

    print(f"\n{YELLOW}Quick start:{NC}\n")
    print(f"  lisa {ex}                      run a ticket")
    print(f"  lisa {ex} --worktree            isolated git worktree")
    print(f"  lisa {ex} --spice --push        enhanced + auto-push")
    print(f"  lisa {ex} --preflight           validate tests before starting")

    if len(ticket_codes) > 1:
        multi = " ".join(f"{c}-100" for c in ticket_codes[:2])
        print(f"  lisa {multi}          run tickets in series")
    else:
        print(f"  lisa {ex} {prefix}-124          run tickets in series")

    print(f"\n{YELLOW}Common flags:{NC}\n")
    print("  --effort low|medium|high       work intensity (default: high)")
    print("  --skip-verify                  skip test/review phases")
    print("  --skip-plan                    use subtasks directly as plan")
    print("  -i / -I                        interactive assumption editing")
    print("  --dry-run                      preview plan without executing")
    print("  --conclusion                   generate review guide for branch")

    print(f"\n{YELLOW}Tips:{NC}\n")
    print("  Create subtasks on your ticket for Lisa to follow as steps")
    print("  Use --worktree to keep your working tree clean")
    print("  Check the Lisa comment on your Linear ticket for progress")
    print()


# --- Main init flow ---


def run_init(yes: bool = False) -> None:
    """Interactive project setup for Lisa."""
    print(f"\n{GREEN}Lisa Init{NC} — configure Lisa for this repository\n")

    # Check if already initialized
    if CONFIG_FILE.exists():
        if yes:
            log(f"Found existing {CONFIG_FILE}, re-initializing (--yes)")
        else:
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

    # --- Linear auth + team detection ---
    linear_authenticated = _try_linear_auth(yes=yes)
    ticket_codes = _detect_ticket_codes(linear_authenticated, yes=yes)
    log(f"Ticket prefixes: {', '.join(ticket_codes)}")

    # --- Config detection ---
    log("Detecting project stack...")
    config = _claude_detect_config()
    if config:
        log("Config generated with Claude")
    else:
        warn("Claude detection failed — opening editor with empty template")
        config = {
            "tests": [{"name": "Tests", "run": "echo 'TODO: add test command'"}],
            "fallback_tools": "Read Edit Write Grep Glob Skill\nBash(git:*) Bash(cd:*) Bash(ls:*) Bash(mkdir:*) Bash(rm:*)",
        }

    config = _ensure_min_fallback_tools(config)

    if not config.get("tests"):
        warn("Could not auto-detect test commands")
        log("You can add them manually after init")

    # Show preview
    _print_config_preview(config)

    # Ask user to confirm
    if yes:
        answer = ""
    else:
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
    try:
        LISA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            f.write("# Lisa stack configuration\n")
            f.write("# See: https://github.com/evenly-energy/lisa#configuration\n")
            f.write(
                "# Override chain: bundled defaults < ~/.config/lisa/config.yaml < .lisa/config.yaml\n\n"
            )
            yaml.dump(config, f, default_flow_style=False, sort_keys=False, width=120)
    except OSError as e:
        error(f"Failed to write {CONFIG_FILE}: {e}")
        sys.exit(1)
    success(f"Wrote {CONFIG_FILE}")

    # --- Skills ---
    print(f"\n{GREEN}Skills{NC} — optional Claude Code skills to enhance Lisa usage\n")

    available_skills = _get_available_skills(ticket_codes)
    for skill_name, skill_info in available_skills.items():
        skill_file = SKILLS_DIR / skill_name / "SKILL.md"
        if skill_file.exists():
            log(f"  {skill_name}: already installed at {skill_file}")
            continue

        print(f"  {YELLOW}{skill_name}{NC}: {skill_info['description']}")
        if not yes:
            try:
                answer = input(f"  Install {skill_name} skill? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if answer in ("n", "no"):
                continue

        if _install_skill(skill_name, skill_info["content"], yes=yes):
            success(f"Installed {skill_name} skill at {SKILLS_DIR / skill_name / 'SKILL.md'}")

    # --- How-to guide ---
    _print_howto(ticket_codes)
