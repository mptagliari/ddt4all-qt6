# Agent instructions

Read `~/vibecoding/AGENTS.md` first: it holds the workspace-wide rules (English-only repositories, safety, git/PR policy) that apply to this project. This file adds to them and wins on conflicts.

## What this repository is

A personal fork of [cedricp/ddt4all](https://github.com/cedricp/ddt4all) (DDT4ALL, a CAN/OBD diagnostic tool) carrying the Qt6/PySide6 work and related fixes. It is upstream code: keep diffs small, do not reformat or translate files, and keep each branch focused so it can become an upstream pull request.

## Remotes and branches

- `origin` = upstream `cedricp/ddt4all` (read-only; no push access).
- `fork` = `mptagliari/ddt4all-qt6` (the fork). The `mptag-code` account does not have push access to it yet; ask the owner for collaborator access before pushing or opening PRs, and never use the owner's personal account instead.
- Fork branches, each one pushed and one concern each: `ecu-list-init-speed`, `tester-present-backoff`, `zip-handle-cache`, `offline-connect-button`, `qt-pyside6-support`, `qt6-integrated`. The `.patch` files in `ddt4all-patches/` are exports of the first three.
- `pyside6-migration-wip` is an **unreviewed snapshot** (PySide6 migration, `diagnostics/` package with the ABS reader, `qt.py`, `core/ecu/ecu_zip.py`, ELM lifecycle tests). It is pushed to the fork as a safety copy only; a backup bundle is at `~/vibecoding/ddt4all-qt6-wip.bundle`. Do not delete either; split it into focused branches before proposing anything upstream.
- Whether upstream received a pull request for any of these branches is not recorded here; the owner opened an issue upstream. Check upstream before assuming.

## Local layout

- This directory is the main checkout (currently on `offline-connect-button`). `ddt4all-eculist`, `ddt4all-tester` and `ddt4all-zipcache` are git worktrees of this repository (one branch each); `ddt4all-qt6-app` is a separate clone of the fork (branch `connection-settings-menu`). All of them are ignored through `.git/info/exclude`. Do not nest new clones here.
- Large local data is untracked and shared: `ecu.zip` (about 460 MB), `json/`, `config.json`. `ddt4all-qt6-app` links to them with symlinks. Never commit them.
- Local-only configuration: `config.json`; `config.json.from-original-clone` is the older copy kept for reference.
- If this directory is moved, run `git worktree repair <worktree paths>` from here and re-point the symlinks in `ddt4all-qt6-app`.

## Commands

- Python 3.8+; use a virtualenv in `venv/` (ignored, recreate it with `python -m venv venv && venv/bin/pip install -e .[dev]`; see `pyproject.toml`).
- Tests: `venv/bin/python -m pytest` (see `tests/`).
- Resources: `scripts/gen_qrc.py` generates the Qt resource module (`generated/resources_rc.py` is generated, do not edit by hand).

## Rules specific to this project

- Diagnostic tools talk to real vehicles. Never send write, reflash, actuator or coding commands to a vehicle or ECU without explicit owner authorization; read-only scans and offline/simulated ELM runs are fine.
- Prefer the offline ELM emulator and recorded sessions for tests; never require a live vehicle in the test suite.
- Keep upstream strings, locale files and license headers intact (GPL-3.0).
