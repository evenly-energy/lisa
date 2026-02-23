# /commit — Commit with conventional commits

## Arguments
Takes an optional message hint: `/commit` or `/commit fix the test runner`

## Instructions

Commit staged and unstaged changes using [Conventional Commits](https://www.conventionalcommits.org/).

### 1. Inspect changes
- Run `git status` and `git diff` (staged + unstaged)
- If no changes exist, stop and say so

### 2. Choose prefix
Pick the prefix based on what changed:

| Prefix | When to use |
|---|---|
| `feat:` | New or changed functionality in the Lisa CLI |
| `fix:` | Bug fix |
| `refactor:` | Code restructuring, no behavior change |
| `test:` | Adding or updating tests |
| `docs:` | Documentation, CLAUDE.md, skills, prompts, schemas |
| `chore:` | Dependencies, CI, release prep, config |

**Breaking changes** (`feat!:`, `fix!:`, etc.): If the change breaks backwards compatibility, ask the user to confirm before using `!`. Never add `!` without asking.

### 3. Write the message
- First line: `<prefix> <concise summary>` — lowercase, no period, imperative mood
- Keep it under 72 characters
- Add a body only if the "why" isn't obvious from the summary
- The `/release` skill uses these prefixes to auto-detect version bumps (`feat:` → minor, `fix:`/others → patch, `!` → major)

### 4. Stage and commit
- Stage relevant files by name (avoid `git add -A`)
- Do not stage files that look like secrets (.env, credentials, etc.)
- Commit using a HEREDOC for the message
- Append `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
