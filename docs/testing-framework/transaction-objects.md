# Transaction objects

When sending a transaction, a transaction object is returned. This object can be used to access
the transaction's properties and wait for it to be mined (if `confirmations=0` set).
Accessing some of the transaction object's properties also performs an implicit `wait()`.

A `tx_callback` can be registered on a `Chain` instance. The callback receives a single argument,
the transaction object. This can be used to process all transactions in a single place.

```python
from wake.testing import *
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
    `tx_callback` is not invoked for transactions with `confirmations=0`!

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
| `effective_gas_price`              | effective gas price of the transaction                                                                                                                            | performs implicit `wait()`                                           |
| `error`                            | native (`pytypes`) revert error, `None` if the transaction succeeded                                                                                              | performs implicit `wait()`                                           |
| `events`                           | list of native (`pytypes`) events emitted by the transaction                                                                                                      | performs implicit `wait()`                                           |
| `from_`                            | `Account` the transaction was sent from                                                                                                                           |                                                                      |
| `gas_limit`                        | gas limit specified in the transaction                                                                                                                            |                                                                      |
| `gas_used`                         | gas used by the transaction                                                                                                                                       | performs implicit `wait()`                                           |
| `nonce`                            | nonce specified in the transaction                                                                                                                                |                                                                      |
| `r`                                | `r` part of the ECDSA signature                                                                                                                                   | performs implicit `wait()`                                           |
| `raw_error`                        | `UnknownTransactionRevertedError` instance, `None` if the transaction succeeded                                                                                   | performs implicit `wait()`                                           |
| `raw_events`                       | list of `UnknownEvent` instances emitted by the transaction                                                                                                       | performs implicit `wait()`                                           |
| `raw_return_value`                 | raw return value of the transaction; `Account` for contract deployment, `bytearray` otherwise                                                                     | performs implicit `wait()`, raises `error` if the transaction failed |
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

EIP-2930 transactions (type `1`) have the following additional properties:

| Property                   | Description                                                                              | Note |
|----------------------------|------------------------------------------------------------------------------------------|------|
| <nobr>`access_list`</nobr> | access list of the transaction (see [EIP-2930](https://eips.ethereum.org/EIPS/eip-2930)) |      |
| `chain_id`                 | chain ID of the transaction                                                              |      |
| `gas_price`                | gas price specified in the transaction                                                   |      |
| `y_parity`                 | `y` parity of the ECDSA signature                                                        |      |

EIP-1559 transactions (type `2`) have the following additional properties:

| Property                                | Description                                                                                                         | Note |
|-----------------------------------------|---------------------------------------------------------------------------------------------------------------------|------|
| `access_list`                           | access list of the transaction (see [EIP-2930](https://eips.ethereum.org/EIPS/eip-2930))                            |      |
| `chain_id`                              | chain ID of the transaction                                                                                         |      |
| `max_fee_per_gas`                       | maximum fee per gas specified in the transaction (see [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559))          |      |
| <nobr>`max_priority_fee_per_gas`</nobr> | maximum priority fee per gas specified in the transaction (see [EIP-1559](https://eips.ethereum.org/EIPS/eip-1559)) |      |
| `y_parity`                              | `y` parity of the ECDSA signature                                                                                   |      |

## Multiple transactions in a single block

It is possible to send multiple transactions in a way that they are mined in the same block. This
can be achieved in the following steps:

1. Disable `automine` on the `Chain` instance
2. Send any number of transactions with `confirmations=0` and `gas_limit="auto"`
3. Re-enable `automine`
4. Call `.mine()` on the `Chain` instance
5. Wait for the block to be mined

```python
from wake.testing import *
from pytypes.contracts.Counter import Counter


@default_chain.connect()
def test_multiple_txs():
    default_chain.set_default_accounts(default_chain.accounts[0])
    counter = Counter.deploy()

    # temporarily disable automine
    with default_chain.change_automine(False):
        tx1 = counter.increment(confirmations=0, gas_limit="auto")
        tx2 = counter.increment(confirmations=0, gas_limit="auto")
        tx3 = counter.increment(confirmations=0, gas_limit="auto")

    default_chain.mine()

    assert tx1.block == tx2.block == tx3.block
```

!!! tip "Changing `automine`"
    While it is possible to change the `automine` property of a `Chain` instance manually, it is not recommended.
    In a case when a test connects to an existing chain and an exception is raised before `automine` is re-enabled,
    the chain will be left in `automine` disabled state. This can be overcome by using the `change_automine` context
    manager.