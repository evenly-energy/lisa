# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-02-13

### Added
- **Linear OAuth login**: `lisa login` for browser-based authentication (no more manual API keys)
- **Layered configuration system**: Deep merge of `defaults/config.yaml` < `~/.config/lisa/config.yaml` < `.lisa/config.yaml`
- **Comprehensive unit test suite**: 210 tests covering core modules (33% coverage)
- **Brace expansion in path globs**: Support patterns like `{src,tests}/**/*.py`
- CI/CD with GitHub Actions (lint job + test matrix for Python 3.11-3.13)
- Pre-commit hooks (ruff, mypy, coverage badge generation)
- Type checking with mypy (clean on 37 source files)
- Coverage tracking and badge (auto-generated to coverage-badge.json)
- Community documentation (CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md)
- .editorconfig for consistent code formatting
- src/lisa/py.typed marker for PEP 561 compliance

### Changed
- **Pre-commit hook failures now auto-retry**: Fix issues instead of bypassing with --no-verify
- Link iteration header to state comment instead of ticket
- Inline test retry filter into test command config
- Fixed type safety in verify.py (bytes/str handling)
- Organized imports across all source files (ruff I001)
- Break circular import by moving constants to lisa.constants

### Fixed
- Pre-commit workflow now fixes failures automatically instead of bypassing validation

## [0.2.1] - 2026-02-13

### Added
- `--preflight` flag for pre-flight checks without executing work

### Changed
- Improved error handling in preflight mode

## [0.2.0] - 2026-02-13

### Added
- Step completion verification before running tests
- Model configuration for review phases

### Changed
- Fixed review model selection bug
- Improved verify phase early exit logic

## [0.1.0] - 2026-02-02

### Added
- Initial release
- Autonomous Linear ticket implementation
- Planning phase with codebase exploration
- Work loop with state machine (SELECT_STEP → EXECUTE_WORK → VERIFY → COMMIT)
- Test/review/fix cycle with Claude Code
- Linear comment state persistence
- Git commit with structured trailers
- Interactive assumption editing
- Worktree support for isolated builds
- Multi-ticket serial processing
- Layered config system (defaults < global < project)
- JSON schema-based structured output
- Conclusion/review guide generation

[Unreleased]: https://github.com/evenly-energy/lisa/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/evenly-energy/lisa/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/evenly-energy/lisa/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/evenly-energy/lisa/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/evenly-energy/lisa/releases/tag/v0.1.0
