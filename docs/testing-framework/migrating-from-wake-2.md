# Migrating from Wake 2.x

Wake 3.x introduces a new deployment module, which gives ability to write deployment scripts in Python.
In order to achieve maximum consistency between the deployment and testing modules, a few breaking changes were introduced.
This document describes the changes and how to migrate from Wake 2.x to Wake 3.x.

## Return value of transaction calls

In Wake 2.x, the return value of a transaction call was a return value of a function called in the transaction.
Using the `return_tx=True` flag, it was possible to return the transaction object itself. With `return_tx=True`, a transaction object was returned immediately after the transaction was sent.
As a consequence, when using `return_tx=True`:

- the transaction revert exception was not automatically raised,
- `chain.tx_callback` was not called for the transaction,
- accessing some transaction fields performed implicit `.wait()`.

With Wake 3.x, the return value of a transaction call is always a transaction object.
Furthermore, the transaction object is returned only after the transaction is mined (unless overridden with `confirmations=0`).
The return value of the `.deploy()` method is still the contract object. To get the transaction object from the `.deploy()` method, use the `return_tx=True` flag.
The `return_tx` flag is no longer supported for other transaction calls.

To get the return value of a transaction call:
```python
# Wake 2.x
ret_val = counter.increment()

# Wake 3.x
ret_val = counter.increment().return_value
```

To get the transaction object immediately without waiting for the transaction to be mined:
```python
# Wake 2.x
tx = counter.increment(return_tx=True)

# Wake 3.x
tx = counter.increment(confirmations=0)
```

To get the transaction object after the transaction is mined:
```python
# Wake 2.x
# tx_callback is not called
# revert exception is not raised
tx = counter.increment(return_tx=True)
tx.wait()

# Wake 3.x
# tx_callback is called
# revert exception is raised if the transaction reverts
tx = counter.increment()
```

The `.deploy()` method behaves the same in Wake 2.x and Wake 3.x:
```python
# Wake 2.x
counter = Counter.deploy()

# Wake 3.x
counter = Counter.deploy()
```

## Default transaction type

Wake 2.x supported only legacy (type 0) transactions. With Wake 3.x, all transaction types are supported and the default transaction type is the latest transaction type supported by the chain (types are prioritized in the following order: 2, 1, 0).

To achieve the same behavior as in Wake 2.x, set `type=0` in all transaction calls:

```python
counter.increment(type=0)
```

or use:

```python
default_chain.default_tx_type = 0
```

to set the default transaction type for the chain.

## `deployment_code()` renamed to `get_creation_code()`

`ContractType.deployment_code()` was renamed to `ContractType.get_creation_code()` in Wake 3.x:

```python
# Wake 2.x
code = Counter.deployment_code()

# Wake 3.x
code = Counter.get_creation_code()
```
