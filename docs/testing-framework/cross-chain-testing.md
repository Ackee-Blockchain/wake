# Cross-chain testing

Woke testing framework supports testing multichain solutions. The API remains the same as for single-chain solutions.
The only difference is that a `Chain` instance must be created for each chain. This instance must be passed to
all API functions that accept a `chain` keyword argument.

`chain` must be specified in the following cases:

- when deploying a contract (e.g. `Counter.deploy(chain=chain1)`),
- when creating an `Account` instance (e.g. `Account(random_address(), chain=chain1)`),
    - including contract instances (e.g. `IERC20(erc20, chain=chain1)`),
- with `random_account()` (e.g. `random_account(chain=chain1)`).

!!! tip "Cross-chain testing and `default_chain`"
    It is highly recommended not to use the `default_chain` global variable in cross-chain tests.
    Leaving it unconnected helps to find bugs in the code when `chain` was forgotten to be passed to a function.

    In this case, `NotConnectedError: Not connected to a chain` is raised.

It is not possible to use `Account` instances bound to different chains than the chain being interacted with.
This is done to prevent accidental misuse of accounts.

```python
from woke.testing import *
from woke.testing.fuzzing import random_account
from pytypes.contracts.Counter import Counter

chain1 = Chain()
chain2 = Chain()

@chain1.connect()
@chain2.connect()
def test_cross_chain():
    owner = random_account(chain=chain2)
    counter1 = Counter.deploy(from_=owner, chain=chain1)
```

The above code snippet will raise `ValueError: from_ account must belong to the chain`.

To overcome this limitation, it is possible to use `Address` of the account instead:

```python
counter1 = Counter.deploy(from_=owner.address, chain=chain1)
```

## Relaying events

In production, cross-chain solutions usually emit events on a source chain. The events are captured by a relayer and appropriate actions are taken on the other chain.

Cross-chain tests have to simulate this behavior. The next code snippet shows an example of how a relay function can be implemented:

```python
from woke.testing import *
from pytypes.contracts.Counter import Counter

chain1 = Chain()
chain2 = Chain()

def relay(other_counter: Counter, events: List):
    for event in events:
        if isinstance(event, Counter.Incremented):
            other_counter.increment()
        elif isinstance(event, Counter.Decremented):
            other_counter.decrement()
        elif isinstance(event, Counter.CountSet):
            other_counter.setCount(event.count)

@chain1.connect()
@chain2.connect()
def test_relay():
    chain1.default_tx_account = chain1.accounts[0]
    chain2.default_tx_account = chain2.accounts[0]

    counter1 = Counter.deploy(chain=chain1)
    counter2 = Counter.deploy(chain=chain2)

    tx = counter1.increment()
    relay(counter2, tx.events)
    assert counter2.count() == 1

    tx = counter2.decrement()
    relay(counter1, tx.events)
    assert counter1.count() == 0

    tx = counter1.setCount(5)
    relay(counter2, tx.events)
    assert counter2.count() == 5
```

A slightly different approach can be to register `tx_callback` on both chains and implement the relay logic there.
