# Migrating from Woke 3.x

In the version 4.0.0, the framework was renamed from Woke to Wake.
This introduced breaking changes in a form of renamed modules (e.g. `woke.testing` -> `wake.testing`) and renamed CLI commands (e.g. `woke test` -> `wake test`).
Except for the name changes, there a few other breaking changes that are described in this document.

## Configuration option changes

The `ignore_paths` configuration options located under `[compiler.solc]` and `[detectors]` namespaces were renamed to `exclude_paths`.
The change was made to better reflect the purpose of the option and to be more consistent with other tools (e.g. [pyright](https://microsoft.github.io/pyright/#/configuration?id=main-configuration-options)).

The `timeout` configuration option located under `[testing]` namespace was renamed to `json_rpc_timeout` and moved to the `[general]` namespace.

The `woke.toml` -> `wake.toml` migration script should automatically rename the options.
The same migration process is also performed in the [Tools for Solidity](https://marketplace.visualstudio.com/items?itemName=AckeeBlockchain.tools-for-solidity) VS Code extension.

## Default accounts

All 4 default accounts for each request type are now set to `chain.accounts[0]` (if available).

It is no longer needed to set the default accounts manually, like this:

```python
default_chain.set_default_accounts(default_chain.accounts[0])
```

## `detect` CLI command

The `detect` CLI command was re-implemented together with the new API for detectors.
To run all detectors, use the `all` subcommand:

```bash
wake detect all
```

See the output of `wake detect --help` for more information.

## `fuzz` CLI command

The `fuzz` CLI command was integrated into the `test` command. In order to run tests using multiple processes, use the `-P` flag to specify the number of processes.

```bash
wake test -P 4
```

`wake test` now always runs tests using the [pytest](https://docs.pytest.org/en) framework (including multiprocessing tests). To run tests without pytest, use the `--no-pytest` flag.

The `-s` shortcut for the `--seed` flag was renamed to `-S` to avoid conflicts with the `-s` pytest flag.

## `may_revert` and `must_revert` context managers

The `may_revert` and `must_revert` now re-raise the caught exception if the exception does not match the expected type or value.
Previously, the context managers would raise an `AssertionError` instead.