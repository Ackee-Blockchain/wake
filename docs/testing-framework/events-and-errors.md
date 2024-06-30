# Events and errors

Wake testing framework provides a way to test events and errors emitted by the tested contract.

## Events

Every Solidity event definition is translated into a Python dataclass with the same name and attributes as the event parameters.

```solidity
event Transfer(
    address indexed from,
    address indexed to,
    uint256 value
);
```

In this case, `from` is a reserved keyword in Python, so it is renamed to `from_` in the dataclass.

```python
@dataclasses.dataclass
class Transfer:
    """
    Attributes:
        from_ (Address): indexed address
        to (Address): indexed address
        value (uint256): uint256
    """
    _abi = {'anonymous': False, 'inputs': [{'indexed': True, 'internalType': 'address', 'name': 'from', 'type': 'address'}, {'indexed': True, 'internalType': 'address', 'name': 'to', 'type': 'address'}, {'indexed': False, 'internalType': 'uint256', 'name': 'value', 'type': 'uint256'}], 'name': 'Transfer', 'type': 'event'}
    origin: Account = dataclasses.field(init=False, compare=False, repr=False)
    original_name = 'Transfer'
    selector = b'\xdd\xf2R\xad\x1b\xe2\xc8\x9bi\xc2\xb0h\xfc7\x8d\xaa\x95+\xa7\xf1c\xc4\xa1\x16(\xf5ZM\xf5#\xb3\xef'

    from_: Address = dataclasses.field(metadata={"original_name": "from"})
    to: Address
    value: uint256
```

### Accessing events

Events can be accessed using the `events` property of transaction objects:

```python
from wake.testing import *
from pytypes.contracts.Counter import Counter


@chain.connect()
def test_events():
    counter = Counter.deploy()
    tx = counter.increment()
    assert tx.events == [Counter.Incremented()]
```

Or in `tx_callback`:

```python
from wake.testing import *
from pytypes.contracts.Counter import Counter


def tx_callback(tx: TransactionAbc):
    for event in tx.events:
        if isinstance(event, Counter.CountSet):
            print(f"Count of Counter({tx.to}) was set to {event.count}")


@chain.connect()
def test_events():
    chain.tx_callback = tx_callback

    counter = Counter.deploy()
    counter.setCount(42)
```

`pytypes` for unused events are not generated.
`tx.events` may also contain `UnknownEvent` instances for events that cannot be recognized from the contract ABI.

!!! info "How Solidity events are encoded"
    `UnknownEvent` instances contain the `topics` and `data` fields.
    `topics` is a list of 32-byte entries where the first entry matches the selector of the event (i.e. Keccak-256 of the event signature).
    `indexed` parameters of the event are encoded in the `topics[1:]` sublist in the same order as they appear in the event definition.
    Other parameters are ABI-encoded in the `data` field.

    `anonymous` events are encoded in the same way, except that the event selector is not included in the `topics` list.

!!! tip "Accessing raw events"
    Transaction objects also offer the `raw_events` property with a list of `UnknownEvent` instances for all events.
    Accessing `raw_events` can be more efficient than accessing `events`.

## Errors

Solidity user-defined errors are translated into Python dataclasses and inherit from `TransactionRevertedError` which inherits from `Exception`.
`TransactionRevertedError` also has a `tx` field that contains a transaction object for the transaction that caused the error.
The `tx` field is set to `None` if the reverted request was not a transaction.

`pytypes` for unused errors are not generated.

```solidity
error NotEnoughFunds(
    uint256 requested,
    uint256 available
);
```

```python
@dataclasses.dataclass
class NotEnoughFunds(TransactionRevertedError):
    """
    Attributes:
        requested (uint256): uint256
        available (uint256): uint256
    """
    _abi = {'inputs': [{'internalType': 'uint256', 'name': 'requested', 'type': 'uint256'}, {'internalType': 'uint256', 'name': 'available', 'type': 'uint256'}], 'name': 'NotEnoughFunds', 'type': 'error'}
    original_name = 'NotEnoughFunds'
    selector = b'\x8c\x90Sh'

    requested: uint256
    available: uint256
```

### Accessing errors

Revert errors are automatically raised in form of exceptions unless a transaction configured to return immediately with `confirmations=0`.

In case of `confirmations=0`, a revert error can be accessed using the `error` property of the transaction object. This performs an implicit `.wait()`.
If the transaction did not revert, `error` is `None`.

```python
from wake.testing import *
from pytypes.contracts.Counter import Counter


@chain.connect()
def test_errors():
    counter = Counter.deploy(from_=chain.accounts[0])

    try:
        counter.addToWhitelist(
            chain.accounts[1],
            from_=chain.accounts[1],
        )
        assert False, "Should have reverted"
    except TransactionRevertedError as e:
        assert e == Counter.NotOwner()
        tx = e.tx
```

Accessing `tx.return_value` in case of a revert automatically raises `tx.error`.

### Internal error types

There are two types of internal errors in Solidity:

- `Error(string)` - a revert error with a string message, e.g. `require(false, "some error")` or `revert("some error")`,
- `Panic(uint256)` - a revert error with a numeric code in case of a failed assertion, division by zero, arithmetic underflow/overflow, etc.

```python
from wake.testing import *
from pytypes.contracts.Counter import Counter


@chain.connect()
def test_errors():
    counter = Counter.deploy()
    try:
        counter.decrement()
        assert False, "Should have reverted"
    except TransactionRevertedError as e:
        assert e == Panic(PanicCodeEnum.UNDERFLOW_OVERFLOW)
        tx = e.tx
```

The full list of panic codes is available in the `PanicCodeEnum` enum:

```python
class PanicCodeEnum(IntEnum):
    GENERIC = 0
    "Generic compiler panic"
    ASSERT_FAIL = 1
    "Assert evaluated to false"
    UNDERFLOW_OVERFLOW = 0x11
    "Integer underflow or overflow"
    DIVISION_MODULO_BY_ZERO = 0x12
    "Division or modulo by zero"
    INVALID_CONVERSION_TO_ENUM = 0x21
    "Too big or negative integer for conversion to enum"
    ACCESS_TO_INCORRECTLY_ENCODED_STORAGE_BYTE_ARRAY = 0x22
    "Access to incorrectly encoded storage byte array"
    POP_EMPTY_ARRAY = 0x31
    ".pop() on empty array"
    INDEX_ACCESS_OUT_OF_BOUNDS = 0x32
    "Out-of-bounds or negative index access to fixed-length array"
    TOO_MUCH_MEMORY_ALLOCATED = 0x41
    "Too much memory allocated"
    INVALID_INTERNAL_FUNCTION_CALL = 0x51
    "Called invalid internal function"
```

### Helper functions

Wake offers two helper functions (context managers) to handle errors - `must_revert` and `may_revert`. Both functions can accept:

- no arguments - any `TransactionRevertedError` is handled,
- a single error type - either `Error`, `Panic` or a user-defined type from `pytypes`,
- a single error instance - an instance of `Error`, `Panic` or a user-defined type from `pytypes`, e.g. `Error("some error")` or `Panic(PanicCodeEnum.UNDERFLOW_OVERFLOW)`,
    - the error raised by the tested contract must exactly match the provided error instance,
- a tuple or list of errors - any mix of error types and error instances.

```python
from wake.testing import *

# handle any Error(str message) or underflow/overflow
with must_revert((Error, Panic(PanicCodeEnum.UNDERFLOW_OVERFLOW))) as e:
    # some code that reverts
    pass

print(e.value)
# get the transaction object (if any)
tx = e.value.tx
```

`e.value` contains the error instance that was raised by the tested contract, or `None` if no error was raised.

!!! tip
    For ease of use, both context managers also accept `str` and `PanicCodeEnum` instances directly, e.g.
    ```python
    with must_revert("some error")
    ```
    or
    ```python
    with must_revert(PanicCodeEnum.UNDERFLOW_OVERFLOW)
    ```

    However, `e.value` will always be an instance of `Error` or `Panic` in this case.
