# Contributing

## Creating a virtual environment

We recommend creating a virtual environment inside of the `woke` subdirectory; we have encountered problems when creating it in the root directory.

```bash
$ cd woke
```

Using [virtualenvwrapper](https://virtualenvwrapper.readthedocs.io):

```bash
$ mkvirtualenv woke
```

Using [venv](https://docs.python.org/3/library/venv.html):

```bash
$ python3 -m venv env
$ source env/bin/activate
```

## Installation

```bash
$ cd woke
$ pip install -e ".[tests,dev]"
```

Pyright, our static type checker, is distributed through npm:

```bash
$ npm i -g pyright
```

## Git hooks

For Unix-like platforms, we provide a script that will set-up git hooks.

After cloning, execute.

```bash
$ chmod +x ./setup-githooks.sh
$ ./setup-githooks.sh
```

