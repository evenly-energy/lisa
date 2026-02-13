# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- CI/CD with GitHub Actions (lint, test matrix for Python 3.11-3.13)
- Pre-commit hooks (ruff, mypy, coverage badge)
- Type checking with mypy
- Coverage tracking and badge
- Community documentation (CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md)
- Issue and PR templates

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

[Unreleased]: https://github.com/evenly-energy/lisa/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/evenly-energy/lisa/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/evenly-energy/lisa/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/evenly-energy/lisa/releases/tag/v0.1.0
