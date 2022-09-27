# Woke

Woke is a Python-based development and testing framework for Solidity.

Features:

- **Vulnerability detectors**

- **LSP server**

- **Fuzzer** - a property-based fuzzer for Solidity smart contracts that allows testers to write their fuzz tests in Python.

## Dependencies

- [Python](https://www.python.org/downloads/release/python-3910/) (version 3.7 or higher)

## Installation

> :warning: **Woke has been moved from `abch-woke` PyPi package to `woke`.**

via `pip`

```shell
pip3 install woke
```

## Features

### Vulnerability detectors

Vulnerability detectors can be run using:
```shell
woke detect
```

### LSP server

Woke implements an [LSP](https://microsoft.github.io/language-server-protocol/) server for Solidity. The only currently supported communication channel is TCP.

Woke LSP server can be run using:

```shell
woke lsp
```

Or with an optional --port argument:

```shell
woke lsp --port 1234
```

All LSP server features can be found in the [documentation](https://ackeeblockchain.com/woke/docs/latest/language-server/).

### Fuzzer

The property-based fuzzer can be installed as an extra dependency. Due to the dependency on [eth-brownie](https://eth-brownie.readthedocs.io/en/stable/), it is recommended to install it into a [virtual environment](https://docs.python.org/3/library/venv.html).

```shell
pip3 install woke[fuzzer]
```

## Documentation & Contribution

Woke documentation can be found [here](https://ackeeblockchain.com/woke/docs).

There you can also find a section on [contributing](https://ackeeblockchain.com/woke/docs/latest/contributing/).

## License

This project is licensed under the [ISC license](https://github.com/Ackee-Blockchain/woke/blob/main/LICENSE).
