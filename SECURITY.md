# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | :white_check_mark: |
| 0.1.x   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report security vulnerabilities to:
- **Email**: dev@evenly.no
- **Subject**: [SECURITY] Lisa - Brief Description

### What to Include

Please include the following information:
- Type of issue (e.g. API key exposure, command injection, etc.)
- Full paths of source file(s) related to the issue
- Location of the affected source code (tag/branch/commit)
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

### Response Timeline

- **Initial response**: Within 48 hours
- **Status update**: Within 7 days
- **Fix timeline**: Depends on severity and complexity

We'll keep you informed about the progress toward a fix and may ask for additional information.

## Security Best Practices

When using Lisa:
- Store API keys in environment variables, never in code
- Use `.gitignore` to exclude `.env` and credential files
- Review Lisa's generated commits before pushing to main
- Use `--dry-run` to preview changes before execution
- Avoid using `--yolo` mode in production environments
