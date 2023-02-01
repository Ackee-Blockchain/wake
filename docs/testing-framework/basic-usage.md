# Basic usage

This guide explains how to run the first test in the Woke testing framework.

## Generating pytypes

The first step is to generate `pytypes` for smart contracts that should be tested. This is done by running the following command:

```shell
woke init pytypes -w
```

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
    Source code for this example is available in the [Woke repository](https://github.com/Ackee-Blockchain/woke/tree/ac1b74b97672557cc51fe1c5fa5cff652f872041/examples/testing).

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
The `@connect` decorator either launches a new development chain or connects to an existing one, if the second argument is specified.
It is possible to connect using:

- a HTTP connection (e.g. `http://localhost:8545`),
- a WebSocket connection (e.g. `ws://localhost:8545`),
- an IPC socket (e.g. `/tmp/anvil.ipc`).

```python
from woke.testing import *

# launch a new development chain
@connect(default_chain)
# or connect to an existing chain
# @connect(default_chain, "ws://localhost:8545")
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

| Argument    | Description                                                                                 |
|-------------|---------------------------------------------------------------------------------------------|
| `from_`     | the address that will be used to deploy the contract (the transaction sender)               |
| `value`     | the amount of Wei to be sent to the contract                                                |
| `gas_limit` | the maximum amount of gas that can be used to deploy the contract (`max`, `auto` or number) |
| `return_tx` | if set to `True`, the full transaction object is returned instead of the contract instance  |
| `chain`     | the chain to which the contract should be deployed                                          |

```python
from woke.testing import *

from pytypes.contracts.Counter import Counter

@connect(default_chain)
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

| Argument       | Description                                                     |
|----------------|-----------------------------------------------------------------|
| `to`           | the address of the contract to which the request should be sent |
| `request_type` | the type of the request (`call` or `tx`)                        |

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

@connect(default_chain)
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
