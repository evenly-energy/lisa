# /release — Create a new Lisa release

## Arguments
Takes an optional version number: `/release 0.4.0` or just `/release`

## Dynamic Context
```
$LAST_TAG = $(git describe --tags --abbrev=0 2>/dev/null || echo "none")
$COMMITS_SINCE = $(git log ${LAST_TAG}..HEAD --oneline 2>/dev/null || git log --oneline)
$DIFF_STAT = $(git diff ${LAST_TAG}..HEAD --stat 2>/dev/null || echo "no previous tag")
```

## Instructions

You are releasing Lisa v{version}. Follow these steps exactly:

### 1. Version resolution (skip if version argument was provided)

When no version argument is provided:
- Get commit subjects since last tag: `git log {last_tag}..HEAD --format="%s"`
- Determine bump type using conventional commit prefixes:
  - **Major** if any commit has `!` after type (e.g. `feat!:`) or contains `BREAKING CHANGE`
  - **Minor** if any commit starts with `feat:`
  - **Patch** otherwise (fix:, refactor:, test:, chore:, docs:, etc.)
- Parse last tag to get current X.Y.Z, compute suggested next version
- Use `AskUserQuestion` to present suggestion:
  - Show the suggested version as the first option
  - Show 1-line rationale (e.g. "Minor: new features detected (feat: add live timers...)")
  - Let user accept or type a custom version via "Other"
- Continue with the resolved version

### 2. Pre-flight checks
- Verify working tree is clean (`git status --porcelain` must be empty)
- Verify on `main` branch
- Verify version argument is valid semver (X.Y.Z)
- Verify tag `v{version}` does not already exist
- If any check fails, stop and explain

### 3. Analyze changes since last tag
- The dynamic context above gives you commit onelines and diff stats
- Read **full commit messages** with `git log {last_tag}..HEAD --format="%H%n%s%n%b%n---"`
- When a commit message is ambiguous or too terse, read the actual changed files to understand what was done
- Group changes into **Added** (new features/capabilities), **Changed** (modifications to existing behavior), **Fixed** (bug fixes)
- Omit trivial commits (merge commits, typo fixes) unless they represent meaningful changes
- Write entries in the same style as existing CHANGELOG.md — bold lead phrase, then description

### 4. Update CHANGELOG.md
- Read current CHANGELOG.md
- Replace `## [Unreleased]` section with empty `## [Unreleased]` followed by the new version section:
  ```
  ## [Unreleased]

  ## [{version}] - {today's date YYYY-MM-DD}

  ### Added
  - ...

  ### Changed
  - ...

  ### Fixed
  - ...
  ```
- Only include sections (Added/Changed/Fixed) that have entries
- Update the comparison links at the bottom:
  - Change `[Unreleased]` link to compare against `v{version}` instead of previous tag
  - Add new version link: `[{version}]: https://github.com/evenly-energy/lisa/compare/v{previous}...v{version}`

### 5. Commit
```bash
git add CHANGELOG.md && git commit -m "chore: release v{version}"
```

### 6. Tag
```bash
git tag v{version}
```

### 7. Push
```bash
git push origin main && git push origin v{version}
```

### 8. GitHub Release
```bash
gh release create v{version} --generate-notes --title "v{version}"
```
