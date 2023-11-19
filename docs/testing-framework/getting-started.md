# Getting started

This guide explains how to run the first test in Wake development and testing framework.

!!! warning "Important"
    Before getting started, make sure to have the latest version of a development chain installed.

    This is especially important in the case of [Anvil](https://github.com/foundry-rs/foundry/tree/master/crates/anvil), because it is under active development.
    To install the latest version of Anvil, run the following command:

    ```shell
    foundryup
    ```

!!! tip
    The command `wake init --example counter` can be used to generate an example project in the empty current working directory.

    Code snippets in this guide are based on the example project.

## Generating pytypes

`pytypes` are Python-native equivalents of Solidity types. They are generated from Solidity source code and used in tests and deployment scripts to interact with smart contracts.

The first step is to generate `pytypes` by running the following command:

```shell
wake init
```

The command prepares `wake.toml` in the current working directory, updates `.gitignore`, prepares a basic directory structure, and generates `pytypes` for all Solidity source files found.

!!! note "Configuring compilation"
    Wake uses default configuration options that should work for most projects.
    However, in some cases, it may be necessary to configure the compilation process.
    For more information, see the [Compilation](../compilation.md) page.

Alternatively, the following commands can be used just to setup the config file and generate `pytypes`:

```shell
wake init config
wake init pytypes -w
```

The `-w` flag tells Wake to watch for changes in the smart contracts and automatically regenerate `pytypes` when a change is detected.

<div id="generating-pytypes-asciinema" style="z-index: 1; position: relative;"></div>
<script>
  window.onload = function(){
    AsciinemaPlayer.create('../generating-pytypes.cast', document.getElementById('generating-pytypes-asciinema'), { preload: true, autoPlay: true, rows: 15 });
}
</script>

When a compilation error occurs, Wake generates `pytypes` for the contracts that were successfully compiled. `pytypes` for the contracts that failed to compile are not generated.

!!! warning "Name collisions in `pytypes`"
    In some cases, a name of a Solidity types may be a keyword in Python or otherwise reserved name. In such cases, Wake will append an underscore to the name of the type. For example, `class` will be renamed to `class_`.

    This also applies to overloaded functions. For example, if a contract has a function `foo` that takes an argument of type `uint256` and another function `foo` that takes an argument of type `uint8`, the generated `pytypes` will contain two functions `foo` and `foo_`.

## Writing the first test

!!! tip
    Solidity source code for all examples in this guide is available in the [Wake repository](https://github.com/Ackee-Blockchain/wake/tree/main/examples/counter).

To collect and execute tests, Wake uses the [pytest](https://docs.pytest.org/en/stable/) framework under the hood.
The test files should start with `test_` or end with `_test.py` to be collected. It is possible to use all the features of the pytest framework like [fixtures](https://docs.pytest.org/en/stable/explanation/fixtures.html).

!!! tip "Connecting to a chain from a fixture"
    In order to interact with a chain in a fixture, the chain must already be connected.
    The best way to achieve this is to prepare a fixture that connects to the chain and use it wherever needed.

    ```python
    @fixture
    def chain():
        if default_chain.connected:
            return default_chain
        else:
            with default_chain.connect():
                yield default_chain
    ```

The recommended project structure is as follows:

```text
.
├── contracts
│   └── Counter.sol
├── pytypes
├── scripts
│   ├── __init__.py
│   └── deploy.py
└── tests
    ├── __init__.py
    └── test_counter.py
```

### Connecting to a chain

In single-chain tests, it is recommended to use the `default_chain` object that is automatically created by Wake.
The `connect` decorator either launches a new development chain or connects to an existing one, if an argument is specified.
It is possible to connect using:

- an HTTP connection (e.g. `http://localhost:8545`),
- a WebSocket connection (e.g. `ws://localhost:8545`),
- an IPC socket (e.g. `/tmp/anvil.ipc`).

```python
from wake.testing import *


# launch a new development chain
@default_chain.connect()
# or connect to an existing chain
# @default_chain.connect("ws://localhost:8545")
def test_counter():
    print(default_chain.chain_id)
```

To run the test, execute the following command:

```shell
wake test tests/test_counter.py -d
```

The `-d` flag tells Wake to attach the Python debugger on test failures.

### Deploying a contract

Every Solidity source file has its equivalent in the `pytypes` directory. These directories form a module hierarchy that is similar to the one in the `contracts` directory.
The `Counter` contract from the previous example is available in the `pytypes.contracts.Counter` module.

Every contract has a `deploy` method that deploys the contract to the chain.
The `deploy` method accepts the arguments that are required by the contract's constructor.
Additionally, it accepts keyword arguments that can be used to configure the transaction that deploys the contract.
All keyword arguments are described in the [Interacting with contracts](./interacting-with-contracts.md) section.

```python
from wake.testing import *

from pytypes.contracts.Counter import Counter


@default_chain.connect()
def test_example():
    counter = Counter.deploy()
    print(counter)
```

### Interacting with a contract

For every public and external function in Solidity source code, Wake generates a Python method in `pytypes`.
These methods can be used to interact with deployed contracts. Generated methods accept the same arguments as the corresponding Solidity functions.
Additional keyword arguments can configure the execution of a function like with the `deploy` method.

```python
from wake.testing import *
from pytypes.contracts.Counter import Counter


@default_chain.connect()
def test_counter():
    owner = default_chain.accounts[0]
    other = default_chain.accounts[1]

    counter = Counter.deploy(from_=owner)

    counter.increment(from_=other)
    assert counter.count() == 1

    # setCount can only be called by the owner
    counter.setCount(10, from_=owner)
    assert counter.count() == 10

    # this will fail because the sender account is not the owner
    with must_revert():
        counter.setCount(20, from_=other)
    assert counter.count() == 10
```
