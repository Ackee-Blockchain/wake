# Getting started

This guide explains how to run the first test in the Woke testing framework.

!!! warning "Important"
    Before getting started, make sure to have the latest version of a development chain installed.

    This is especially important in the case of [Anvil](https://github.com/foundry-rs/foundry/tree/master/anvil), because it is under active development.
    To install the latest version of Anvil, run the following command:

    ```shell
    foundryup
    ```

## Generating pytypes

`pytypes` are Python-native equivalents of Solidity types. They are generated from a Solidity source code and are used in tests to interact with smart contracts.

The first step is to generate `pytypes` by running the following command:

```shell
woke init pytypes -w
```

!!! note "Configuring compilation"
    Woke uses default configuration options that should work for most projects.
    However, in some cases, it may be necessary to configure the compilation process.
    For more information, see the [Configuration](../configuration.md) page.

This command will create a `pytypes` directory in the current working directory. The `-w` flag tells Woke to watch for changes in the smart contracts and automatically regenerate the `pytypes` when a change is detected.

<div id="generating-pytypes-asciinema" style="z-index: 1; position: relative;"></div>
<script>
  window.onload = function(){
    AsciinemaPlayer.create('../generating-pytypes.cast', document.getElementById('generating-pytypes-asciinema'), { preload: true, autoPlay: true, rows: 15 });
}
</script>

When a compilation error occurs, Woke generates `pytypes` for the contracts that were successfully compiled. `pytypes` for the contracts that failed to compile are not generated.

## Writing the first test

!!! tip
    Solidity source code for all examples in this guide is available in the [Woke repository](https://github.com/Ackee-Blockchain/woke/tree/main/examples/testing).

To collect and execute tests, Woke uses the [pytest](https://docs.pytest.org/en/stable/) framework under the hood.
The test files should start with `test_` or end with `_test.py` to be collected. It is possible to use all the features of the pytest framework like [fixtures](https://docs.pytest.org/en/stable/explanation/fixtures.html).

The recommended project structure is as follows:

```text
.
├── contracts
│   └── Counter.sol
├── pytypes
└── tests
    ├── __init__.py
    └── test_counter.py
```

### Connecting to a chain

In single-chain tests, it is recommended to use the `default_chain` object that is automatically created by Woke.
The `connect` decorator either launches a new development chain or connects to an existing one, if the second argument is specified.
It is possible to connect using:

- a HTTP connection (e.g. `http://localhost:8545`),
- a WebSocket connection (e.g. `ws://localhost:8545`),
- an IPC socket (e.g. `/tmp/anvil.ipc`).

```python
from woke.testing import *

# launch a new development chain
@default_chain.connect()
# or connect to an existing chain
# @default_chain.connect("ws://localhost:8545")
def test_counter():
    print(default_chain.chain_id)
```

To run the test, execute the following command:

```shell
woke test tests/test_counter.py -d
```

The `-d` flag tells Woke to attach the Python debugger on test failures.

### Deploying a contract

Every Solidity source file has its equivalent in the `pytypes` directory. These directories form a module hierarchy that is similar to the one in the `contracts` directory.
The `Counter` contract from the previous example is available in the `pytypes.contracts.Counter` module.

Every contract has a `deploy` method that deploys the contract to the chain.
The `deploy` method accepts the arguments that are required by the contract's constructor.
Additionally, it accepts the following keyword arguments:

| Argument    | Description                                                                                                    |
|-------------|----------------------------------------------------------------------------------------------------------------|
| `from_`     | `Address`, `Account` or a hex address string that will be used to deploy the contract (the transaction sender) |
| `value`     | amount of Wei to be sent to the contract                                                                       |
| `gas_limit` | maximum amount of gas that can be used in the transaction (`max`, `auto` or number)                            |
| `return_tx` | `True` to return the full transaction object, `False` to return the return value (contract instance)           |
| `chain`     | `Chain` to which the contract should be deployed                                                               |

!!! warning "Sending transactions from any account"
    The `from_` argument can be used to send transactions from any account (including contract) or address.
    However, this may come at a cost of decreased performance (see [Performance considerations](performance-considerations.md)).

    **When sending transactions from an account with code (contract), the contract behaves as if it had no code during the execution of the transaction!**

```python
from woke.testing import *

from pytypes.contracts.Counter import Counter

@default_chain.connect()
def test_example():
    counter = Counter.deploy(from_=default_chain.accounts[0])
    print(counter)
```

### Interacting with a contract

Woke testing framework distinguishes between two types of interactions with a contract:

- **calls** - read-only requests that do not change the state of the blockchain,
- **transactions** - requests that change the state of the blockchain.

By default, Woke uses **calls** to execute pure and view functions. It uses **transactions** to execute all other functions.

There are two more keyword arguments that the `deploy` method does not accept:

| Argument       | Description                                                                                      |
|----------------|--------------------------------------------------------------------------------------------------|
| `to`           | `Address`, `Account` or a hex address string of the contract to which the request should be sent |
| `request_type` | type of the request (`call` or `tx`)                                                         |

!!! tip
    The `to` argument can be used to override the address of the contract that is being called.
    This can be useful when a contract should be called through a proxy contract.

    ```python
    contract.initialize(owner, to=proxy)
    ```




If no `from_` argument is specified:

- `default_chain.default_call_account` is used to execute **calls**,
- `default_chain.default_tx_account` is used to execute **transactions**.

`default_call_account` is initialized to the first account in the chain's account list.
`default_tx_account` is left unset by default.

```python
from woke.testing import *

from pytypes.contracts.Counter import Counter

@default_chain.connect()
def test_counter():
    default_chain.default_tx_account = default_chain.accounts[1]

    counter = Counter.deploy(from_=default_chain.accounts[0])
    counter.increment()
    assert counter.count() == 1
    
    # increment performed as a call does not change the state
    counter.increment(request_type="call")
    assert counter.count() == 1

    # setCount can only be called by the owner
    counter.setCount(10, from_=default_chain.accounts[0])
    assert counter.count() == 10
    
    # this will fail because the default account is not the owner
    with must_revert():
        counter.setCount(20)
    assert counter.count() == 10
```
