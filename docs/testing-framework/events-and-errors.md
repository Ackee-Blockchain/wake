# Events and errors

Woke testing framework provides a way to test events and errors emitted by the tested contract.

## Events

Events can be accessed using the `events` property of transaction objects.

Transaction objects can be either obtained directly as a return value for function executions that specify `return_tx=True`:

```python
from woke.testing import *
from pytypes.contracts.Counter import Counter

@connect(default_chain)
def test_events():
    default_chain.default_tx_account = default_chain.accounts[0]

    counter = Counter.deploy()
    tx = counter.increment(return_tx=True)
    assert tx.events == [Counter.Incremented()]
```

Or in `tx_callback` for function executions with `return_tx=False`:

```python
from woke.testing import *
from pytypes.contracts.Counter import Counter

def tx_callback(tx: TransactionAbc):
    for event in tx.events:
        if isinstance(event, Counter.CountSet):
            print(f"Count of Counter({tx.to}) was set to {event.count}")

@connect(default_chain)
def test_events():
    default_chain.default_tx_account = default_chain.accounts[0]
    default_chain.tx_callback = tx_callback

    counter = Counter.deploy()
    counter.setCount(42)
```

`tx.events` may also contain `UnknownEvent` instances for events that cannot be recognized from the contract ABI.

!!! info "How Solidity events are encoded"
    `UnknownEvent` instances contain the `topics` and `data` fields.
    `topics` is a list of 32-byte entries where the first entry matches the selector of the event (i.e. Keccak-256 of the event signature).
    `indexed` parameters of the event are encoded in the `topics[1:]` sublist in the same order as they appear in the event definition.
    Other parameters are ABI-encoded in the `data` field.

!!! tip "Accessing raw events"
    Transaction objects also offer the `raw_events` property with a list of `UnknownEvent` instances for all events, including those that can be recognized from the contract ABI.
    Accessing `raw_events` can be more efficient than accessing `events`.

## Errors

Revert errors are automatically raised in form of exceptions with `return_tx=False`.

In case of `return_tx=True`, a revert error can be accessed using the `error` property of the transaction object.
If the transaction did not revert, `error` is `None`.

```python
from woke.testing import *
from pytypes.contracts.Counter import Counter

@connect(default_chain)
def test_errors():
    default_chain.default_tx_account = default_chain.accounts[0]

    counter = Counter.deploy()
    tx = counter.decrement(return_tx=True)
    assert tx.error == Panic(PanicCodeEnum.UNDERFLOW_OVERFLOW)
```

Accessing `tx.return_value` in case of a revert automatically raises `tx.error`.

### Error types

There are two types of internal errors in Solidity:

- `Error(string)` - a revert error with a string message, e.g. `require(false, "some error")` or `revert("some error")`,
- `Panic(uint256)` - a revert error with a numeric code in case of a failed assertion, division by zero, arithmetic underflow/overflow, etc.

Additionally, Woke supports user-defined error types. These are generated in `pytypes` in the same namespace (module) as in the original Solidity project.

```python
from woke.testing import *
from pytypes.contracts.Counter import Counter

@connect(default_chain)
def test_errors():
    counter = Counter.deploy(from_=default_chain.accounts[0])
    tx = counter.addToWhitelist(
        default_chain.accounts[1],
        from_=default_chain.accounts[1],
        return_tx=True,
    )
    assert tx.error == Counter.NotOwner()
```

### Helper functions

Woke offers two helper functions (context managers) to handle errors - `must_revert` and `may_revert`. Both functions can accept:

- no arguments - any `TransactionRevertedError` is handled,
- a single error type - either `Error`, `Panic` or a user-defined type from `pytypes`
- a single error instance - an instance of `Error`, `Panic` or a user-defined type from `pytypes`, e.g. `Error("some error")` or `Panic(PanicCodeEnum.UNDERFLOW_OVERFLOW)`,
    - the error raised by the tested contract must exactly match the provided error instance,
- a tuple or list of errors - any mix of error types and error instances.

```python
from woke.testing import *

# handle any Error(str message) or underflow/overflow
with must_revert((Error, Panic(PanicCodeEnum.UNDERFLOW_OVERFLOW))) as e:
    # some code that reverts
    pass

print(e.value)
```

`e.value` contains the error instance that was raised by the tested contract, or `None` if no error was raised.