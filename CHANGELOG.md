# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `volar sync` downloads Tienda Volar (one category, Tecnología by default) and the Itaú
  Volar catalog into a local SQLite history.
- `volar search`, `show`, `changes` and `sql` to query it; `search` and `show` take `--json`.
- Blocked or challenged requests exit with code 3, separate from parse errors (code 1).
- dev-standards baseline: CI, pre-commit, Dependabot.

### Changed
- Requires Python 3.15.
- Logging goes through the shared `logger` package, still on stderr.
