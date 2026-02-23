# /release — Create a new Lisa release

## Arguments
Takes a version number: `/release 0.4.0`

## Dynamic Context
```
$LAST_TAG = $(git describe --tags --abbrev=0 2>/dev/null || echo "none")
$COMMITS_SINCE = $(git log ${LAST_TAG}..HEAD --oneline 2>/dev/null || git log --oneline)
$DIFF_STAT = $(git diff ${LAST_TAG}..HEAD --stat 2>/dev/null || echo "no previous tag")
```

## Instructions

You are releasing Lisa v{version}. Follow these steps exactly:

### 1. Pre-flight checks
- Verify working tree is clean (`git status --porcelain` must be empty)
- Verify on `main` branch
- Verify version argument is valid semver (X.Y.Z)
- Verify tag `v{version}` does not already exist
- If any check fails, stop and explain

### 2. Analyze changes since last tag
- The dynamic context above gives you commit onelines and diff stats
- Read **full commit messages** with `git log {last_tag}..HEAD --format="%H%n%s%n%b%n---"`
- When a commit message is ambiguous or too terse, read the actual changed files to understand what was done
- Group changes into **Added** (new features/capabilities), **Changed** (modifications to existing behavior), **Fixed** (bug fixes)
- Omit trivial commits (merge commits, typo fixes) unless they represent meaningful changes
- Write entries in the same style as existing CHANGELOG.md — bold lead phrase, then description

### 3. Update CHANGELOG.md
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

### 4. Commit
```bash
git add CHANGELOG.md && git commit -m "chore: release v{version}"
```

### 5. Tag
```bash
git tag v{version}
```

### 6. Push (ask confirmation)
Ask the user before running:
```bash
git push origin main && git push origin v{version}
```

### 7. GitHub Release (ask confirmation)
Ask the user before running:
```bash
gh release create v{version} --generate-notes --title "v{version}"
```
