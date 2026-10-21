# Contributing

Keep the public API small, preserve original order, and avoid required runtime
dependencies. Include a focused regression test for behavior changes. Do not add
tests with fixed wall-clock performance limits; use the benchmark runner instead.

## Development

Use Python 3.10 or newer:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest --cov=whyempty --cov-report=term-missing
python -m ruff check .
python -m ruff format --check .
python -m mypy
python examples/basic_usage.py
python examples/audit_usage.py
```

Coverage includes branches and must reach at least 95% for the library. CI runs
tests on CPython 3.10 through 3.15, checks formatting and types, and validates both
source and wheel distributions.

## Preparing a release

Synchronize the version in `pyproject.toml` and `src/whyempty/__init__.py`, and
update `CHANGELOG.md` for each release. Run all checks above. Build from a clean
checkout with an absent or empty `dist/` directory so globs cannot mix versions:

```sh
python -m build
python -m twine check dist/*
python -m pip install --force-reinstall --no-deps dist/*.whl
```

Inspect the archives to confirm that code, `py.typed`, metadata, README and the MIT
license are present. Confirm that `dist/` contains exactly one wheel and one
source distribution for the intended version; never upload stale artifacts.

### Publishing with GitHub Actions

The default manual publication method is PyPI Trusted Publishing. In the PyPI
project's **Publishing** settings, register this GitHub publisher:

- Owner: `giovannyTorres`
- Repository: `whyempty`
- Workflow filename: `publish.yml`
- Environment: leave blank (this workflow does not select an environment)

Registration is a separate PyPI account operation; adding a workflow does not
register the publisher. After registration, open **Actions → Publish to PyPI →
Run workflow**, select the reviewed commit on `main`, keep
`trusted-publishing`, and run it. GitHub supplies short-lived OpenID Connect
credentials; no PyPI API token is needed for this method.

For a project still migrating its publisher registration, explicitly select
`api-token` using the existing repository Actions secret `TWINE_PASSWORD`.
Legacy `release/pypi-*` branch pushes also select this token method. Never put
the token in source code, issues, chat, or workflow inputs. Once Trusted
Publishing is verified, remove the legacy token and branch trigger.

Both methods run tests, coverage, lint and type checks, build distributions,
and validate them before upload. Ordinary pushes to `main` do not publish.
Verify the workflow result and the version from a fresh environment. PyPI
distributions cannot be replaced; increment the version for every release.

### Publishing locally

Confirm package-name ownership on TestPyPI and PyPI before uploading. These are
manual maintainer commands for an authorized release:

```sh
python -m twine upload --repository testpypi dist/*
python -m pip install --index-url https://test.pypi.org/simple/ --no-deps whyempty==0.2.1
# After verifying the TestPyPI installation and approving the release:
python -m twine upload dist/*
```

Use an API token through Twine's supported credential mechanisms; never commit
tokens or place them in command-line arguments. PyPI releases cannot be replaced
in place, so inspect and test the exact archives before uploading.
