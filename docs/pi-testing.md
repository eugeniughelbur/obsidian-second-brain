# Testing the Pi adapter

This doc covers testing the Pi adapter only. It does not cover the internal
vault logic (that is exercised by the broader `tests/` suite and CLI smoke
tests).

## Run the Pi build

```bash
bash scripts/build.sh --platform pi
```

Inspect the output:

```bash
find dist/pi -maxdepth 4 -type f | sort
```

You should see:

- `dist/pi/package.json`
- `dist/pi/.pi/prompts/*.md`
- `dist/pi/.pi/skills/obsidian-second-brain/SKILL.md`
- `dist/pi/.pi/skills/obsidian-second-brain/references/*.md`
- `dist/pi/.pi/skills/obsidian-second-brain/scripts/*.py`

## Run the Pi smoke test

```bash
pytest -q tests/test_smoke.py::test_pi_build_generates_package -v
```

## Research toolkit setup

If you run any `/research`, `/x-read`, `/youtube`, `/notebooklm`, or `/podcast`
prompt template, copy `.env.example` to `~/.config/obsidian-second-brain/.env`,
set permissions to `600`, and fill in the required API keys. Pi reads the same
environment variables as the other platforms.

## Coverage note

The adapter tests are smoke tests that run the build script as a subprocess.
Because pytest-cov only traces in-process Python, these tests do not appear in
the Python coverage report. Coverage for the Pi adapter is measured by the
assertions in `test_pi_build_generates_package`, which validate:

- `package.json` exists and has the correct `pi` manifest
- every command produces a prompt template with frontmatter
- the discovery skill has valid Agent Skills frontmatter
- Claude-specific paths are rewritten to the Pi layout

To run the Python-coverage report for the importable modules:

```bash
pytest -q --cov=scripts --cov=integrations --cov-report=term-missing
```
