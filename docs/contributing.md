# Contributing

## Creating a virtual environment

### Using [Poetry](https://python-poetry.org)

```bash
poetry shell
```

### Using [venv](https://docs.python.org/3/library/venv.html)

```bash
python3 -m venv env
source env/bin/activate
```

### Using [virtualenvwrapper](https://virtualenvwrapper.readthedocs.io)

```bash
mkvirtualenv wake
```

## Installation

### Using [Poetry](https://python-poetry.org)

```bash
poetry install -E tests -E dev
```

### Using [pip](https://pip.pypa.io)

```bash
pip install -e ".[tests,dev]"
```

### Other dependencies

Pyright, our static type checker, is distributed through npm:

```bash
npm i -g pyright
```

## Git hooks

For Unix-like platforms, we provide git hooks to help with development.

After cloning, execute:

```bash
chmod +x ./setup-githooks.sh
./setup-githooks.sh
```

Git hooks automatically run these commands when you commit:

- [gitmoji-fuzzy-hook](https://gitlab.com/raabf/gitmoji-fuzzy-hook) git prepare-commit-msg hook to help you choose a gitmoji
- `pytest tests -m "not slow"` when the `WAKE_HOOKS_RUN_ALL_TESTS` environment variable is not set (`pytest tests` is run otherwise)
- `black` on Python files being committed
- `isort` on Python files being committed
- `pyright` on Python files being committed
- `mkdocs build --strict` to make sure the documentation does not contain errors

Any unstaged changes and untracked files are stashed before running the git pre-commit hook. After the commit is made, the stashed changes are popped from the stash. If this leads to a merge conflict, the stashed changes are left at the top of the stash.
