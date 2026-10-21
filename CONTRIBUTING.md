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
```

Coverage includes branches and must reach at least 95% for the library. CI runs
tests on CPython 3.10 through 3.15, checks formatting and types, and validates both
source and wheel distributions.

## Preparing a release

Version 0.1.0 is prepared for publication; this repository does not automatically
publish releases. Synchronize the version in `pyproject.toml` and
`src/whyempty/__init__.py` for subsequent releases. Run all checks above, then:

```sh
python -m build
python -m twine check dist/*
python -m pip install --force-reinstall --no-deps dist/whyempty-0.1.0-py3-none-any.whl
```

Inspect the archives to confirm that code, `py.typed`, metadata, README and the MIT
license are present. Build from a clean checkout so `dist/` contains only the
intended version; never upload stale artifacts.

Publication requires the maintainer's explicit authorization and credentials.
Confirm package-name ownership on TestPyPI and PyPI before uploading. These are
manual maintainer commands, **not steps to run while implementing the library**:

```sh
python -m twine upload --repository testpypi dist/*
python -m pip install --index-url https://test.pypi.org/simple/ --no-deps whyempty==0.1.0
# After verifying the TestPyPI installation and approving the release:
python -m twine upload dist/*
```

Use an API token through Twine's supported credential mechanisms; never commit
tokens or place them in command-line arguments. PyPI releases cannot be replaced
in place, so inspect and test the exact archives before uploading.
