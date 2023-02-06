# Transaction objects

When sending a transaction, either a return value or a full transaction object can be returned.
The default behavior is to return the return value. This can be changed by setting the `return_tx`
keyword argument to `True`.

When returning a transaction object, it is not waited for the transaction to be mined. This can be
done by calling `wait()` on the transaction object:

```python
tx = counter.increment(return_tx=True)
tx.wait()
```

Accessing some of the transaction object's properties also performs an implicit `wait()`.

!!! tip "Generating `pytypes` with `return_tx=True`"
    It is possible to generate `pytypes` with `return_tx=True` as the default behavior.

    ```shell
    woke init pytypes --return-tx
    ```

    It should be noted that this does not change the default `return_tx` value of the low-level
    `transact` method. This method is not generated in `pytypes`, but inherited from `Account` and
    will use the default `False` value.

Alternatively, `tx_callback` can be registered on a `Chain` instance. The callback receives a single
argument, the transaction object. This can be used to process all transactions in a single place.

```python
from woke.testing import *
from pytypes.contracts.Counter import Counter

def tx_callback(tx: TransactionAbc):
    print(tx.console_logs)

@default_chain.connect()
def test_callback():
    default_chain.tx_callback = tx_callback

    counter = Counter.deploy(from_=default_chain.accounts[0])
    counter.increment(from_=default_chain.accounts[0])
```

!!! warning
    `tx_callback` is not invoked for transactions with `return_tx=True`!

## Transaction properties

Every transaction object has the following properties:

| Property                           | Description                                                                                                                                                       | Note                                                                 |
|------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| `block`                            | `Block` the transaction was mined in                                                                                                                              | performs implicit `wait()`                                           |
| `call_trace`                       | `CallTrace` instance representing the call trace of the transaction                                                                                               | performs implicit `wait()`                                           |
| `chain`                            | `Chain` the transaction was sent to                                                                                                                               |                                                                      |
| `console_logs`                     | list of `console.log` calls made by the transaction                                                                                                               | performs implicit `wait()`                                           |
| <nobr>`cumulative_gas_used`</nobr> | gas consumed by this and all previous transactions in the same block                                                                                              | performs implicit `wait()`                                           |
| `data`                             | data sent in the transaction                                                                                                                                      |                                                                      |
| `error`                            | native (`pytypes`) revert error, `None` if the transaction succeeded                                                                                              | performs implicit `wait()`                                           |
| `events`                           | list of native (`pytypes`) events emitted by the transaction                                                                                                      | performs implicit `wait()`                                           |
| `from_`                            | `Account` the transaction was sent from                                                                                                                           |                                                                      |
| `gas_limit`                        | gas limit specified in the transaction                                                                                                                            |                                                                      |
| `gas_used`                         | gas used by the transaction                                                                                                                                       | performs implicit `wait()`                                           |
| `nonce`                            | nonce specified in the transaction                                                                                                                                |                                                                      |
| `r`                                | `r` part of the ECDSA signature                                                                                                                                   | performs implicit `wait()`                                           |
| `raw_error`                        | `UnknownTransactionRevertedError` instance, `None` if the transaction succeeded                                                                                   | performs implicit `wait()`                                           |
| `raw_events`                       | list of `UnknownEvent` instances emitted by the transaction                                                                                                       | performs implicit `wait()`                                           |
| `return_value`                     | return value of the transaction                                                                                                                                   | performs implicit `wait()`, raises `error` if the transaction failed |
| `s`                                | `s` part of the ECDSA signature                                                                                                                                   | performs implicit `wait()`                                           |
| `status`                           | status of the transaction, `1` for success, `0` for failure, `-1` for pending                                                                                     |                                                                      |
| `to`                               | `Account` the transaction was sent to                                                                                                                             |                                                                      |
| `tx_hash`                          | string hash of the transaction                                                                                                                                    |                                                                      |
| `tx_index`                         | index of the transaction in the block                                                                                                                             | performs implicit `wait()`                                           |
| `type`                             | type of the transaction, `0` for legacy, `1` for [EIP-2930](https://eips.ethereum.org/EIPS/eip-2930), `2` for [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559) |                                                                      |
| `value`                            | amount of Wei sent in the transaction                                                                                                                             |                                                                      |

Legacy transactions (type `0`) have the following additional properties:

| Property              | Description                            | Note                       |
|-----------------------|----------------------------------------|----------------------------|
| `gas_price`           | gas price specified in the transaction |                            |
| `v`                   | ECDSA signature recovery ID            |                            |

!!! info
    Only legacy transactions are currently supported.

## Multiple transactions in a single block

It is possible to send multiple transactions in a way that they are mined in the same block. This
can be achieved in the following steps:

1. Disable `automine` on the `Chain` instance
2. Send any number of transactions with `return_tx=True` and `gas_limit="auto"`
3. Re-enable `automine`
4. Call `.mine()` on the `Chain` instance
5. Wait for the block to be mined

```python
from woke.testing import *
from pytypes.contracts.Counter import Counter

@default_chain.connect()
def test_multiple_txs():
    default_chain.default_tx_account = default_chain.accounts[0]
    counter = Counter.deploy()

    # temporarily disable automine
    with default_chain.change_automine(False):
        tx1 = counter.increment(return_tx=True, gas_limit="auto")
        tx2 = counter.increment(return_tx=True, gas_limit="auto")
        tx3 = counter.increment(return_tx=True, gas_limit="auto")

    default_chain.mine()

    assert tx1.block == tx2.block == tx3.block
```

!!! tip "Changing `automine`"
    While it is possible to change the `automine` property of a `Chain` instance manually, it is not recommended.
    In a case when a test connects to an existing chain and an exception is raised before `automine` is re-enabled,
    the chain will be left in `automine` disabled state. This can be overcome by using the `change_automine` context
    manager.