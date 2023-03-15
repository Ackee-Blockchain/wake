# Interacting with contracts

Contracts can be interacted with either using methods generated in `pytypes` or using low-level methods.

## Request types

There are 4 low-level methods that represent different request types:

- `tx` - a request that sends a transaction (even if the function being called does not modify the blockchain state),
- `call` - a request that returns the return value of the function being called, does not modify the blockchain state (even if the function being called modifies the blockchain state),
- `estimate` - a request that returns an estimated amount of gas needed to perform the transaction,
- `access_list` - a request that returns an access list (addresses and storage keys, see [EIP-2930](https://eips.ethereum.org/EIPS/eip-2930)) and an estimated amount of gas needed to perform the transaction when the access list is used.

The low-level methods are named `.transact()`, `.call()`, `.estimate()`, and `.access_list()` respectively.
Each request type has its default account used when no `from_` argument is provided. The default accounts are properties of the `Chain` object:

- `chain.default_tx_account` for `tx` request type, `None` by default,
- `chain.default_call_account` for `call` request type, set to `chain.accounts[0]` by default,
- `chain.default_estimate_account` for `estimate` request type, `None` by default,
- `chain.default_access_list_account` for `access_list` request type, `None` by default.

The default accounts can be changed by assigning a new value to the corresponding property or by using the `set_default_accounts()` method.

```python
from woke.testing import *

@default_chain.connect()
def test_accounts():
    # assign each default account manually
    default_chain.default_tx_account = default_chain.accounts[0]
    # default_chain.default_call_account is already set to default_chain.accounts[0]
    default_chain.default_call_account = default_chain.accounts[0]
    default_chain.default_estimate_account = default_chain.accounts[0]
    default_chain.default_access_list_account = default_chain.accounts[0]

    # or assign all default accounts at once
    default_chain.set_default_accounts(default_chain.accounts[0])
```

!!! note
    It is recommended to set `default_estimate_account` and `default_access_list_account` to the same account as `default_tx_account` to ensure that the returned gas estimate is accurate.

In `pytypes`, the default request type is `tx` for non-pure non-view functions and `call` for pure and view functions.

```python
from woke.testing import *
from pytypes.contracts.Counter import Counter

@default_chain.connect()
def test_accounts():
    default_chain.set_default_accounts(default_chain.accounts[0])
    counter = Counter.deploy()

    # performs a call
    count = counter.count()

    # sends a transaction
    tx = counter.increment()
```

The request type can be changed using the `request_type` flag.

```python
# does not increment the counter
ret_val = counter.increment(request_type="call")

# "tx" request type is the default for non-pure non-view functions
tx = counter.increment(request_type="tx")

# amount of gas needed to send as a transaction
gas_estimate = counter.increment(request_type="estimate")

# access list and amount of gas needed to send as a transaction
access_list, gas_estimate = counter.increment(request_type="access_list")
```

The `call` request type used on the `.deploy()` method returns runtime code of the contract that would be deployed if the method was called with `tx` request type.

```python
# does not deploy the contract
runtime_code = Counter.deploy(request_type="call")

# deploys the contract and returns the contract instance, the default behavior
counter = Counter.deploy(request_type="tx")

# deploys the contract and returns the transaction object
tx = Counter.deploy(request_type="tx", return_tx=True)

# amount of gas needed to deploy the contract
gas_estimate = Counter.deploy(request_type="estimate")

# access list and amount of gas needed to deploy the contract
access_list, gas_estimate = Counter.deploy(request_type="access_list")
```

!!! warning
    The `call` request type does not currently work for `deploy` methods with Anvil. It always returns empty bytes.

## Keyword arguments

Both methods generated in `pytypes` and low-level methods accept the following keyword arguments common for all request types:

| Argument                   | Description                                                                                                                                |
|----------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| `from_`                    | `Account` or `Address` used as a sender of a transaction/call. If not provided, the default account for the request type will be used.     |
| `value`                    | Amount of Ether to be sent. Can be either an `int` in Wei or a string with a unit (e.g. `"1 ether"`).                                      |
| `gas_limit`                | Maximum amount of gas that can be consumed by the transaction.                                                                             |
| `gas_price`                | Gas price to be used for type 0 and type 1 transactions. Can be either an `int` in Wei or a string with a unit (e.g. `"10 gwei"`).         |
| `max_fee_per_gas`          | Maximum fee per gas to be used for type 2 transactions. Can be either an `int` in Wei or a string with a unit (e.g. `"10 gwei"`).          |
| `max_priority_fee_per_gas` | Maximum priority fee per gas to be used for type 2 transactions. Can be either an `int` in Wei or a string with a unit (e.g. `"10 gwei"`). |
| `access_list`              | Access list to be used for type 1 and type 2 transactions. See [EIP-2930](https://eips.ethereum.org/EIPS/eip-2930) for more information.   |
| `type`                     | Transaction type to be used. Can be either `0`, `1`, or `2`.                                                                               |

Low-level methods also accept the `data` keyword argument (of type `bytes` or `bytearray`) that can be used to specify the data to be sent to a contract.

!!! tip "Encoding data for low-level calls and transactions"
    To prepare the `data` payload, the `Abi` helper class can be used. It offers the same ABI encoding
    functions as the `abi` global object in Solidity.

    ```python
    from woke.testing import *
    from pytypes.contracts.Counter import Counter

    @default_chain.connect()
    def test_low_level_transact():
        default_chain.default_tx_account = default_chain.accounts[0]

        counter = Counter.deploy()

        # execute counter.setCount(100) using a low-level transaction
        counter.transact(data=Abi.encode_call(Counter.setCount, [100]))
        assert counter.count() == 100
    ```

Methods generated in `pytypes` accept the `to` keyword argument (of type `Account`, `Address` or hex-encoded string address) that can be used to override the address of the contract being called.

!!! tip "Calling contracts through a proxy"
    Using the `to` keyword argument can be useful when a contract should be called through a proxy contract.

    ```python
    contract.initialize(owner, to=proxy)
    ```

## `tx` request type

The `tx` request type is used to send a transaction. It accepts one more keyword argument, `confirmations`, that can be used to specify the number of blocks that should be mined before a transaction object is returned.
Setting `confirmations` to `0` returns a transaction object immediately after the transaction is sent.


!!! warning "Sending transactions from any account"
    The `from_` argument can be used to send transactions from any account (including contract) or address.
    However, this may come at a cost of decreased performance (see [Performance considerations](performance-considerations.md)).

    **When sending transactions from an account with code (contract), the contract behaves as if it had no code during the execution of the transaction!**

## `call` request type

The `call` request type is used to execute a call. It accepts one more keyword argument, `block`, that can be used to specify the number of the block to be used as a context for the call.
The default value is `latest` which means that the call will be executed in the context of the latest block.

## `estimate` request type

The `estimate` request type is used to estimate the amount of gas needed to execute a transaction. It accepts one more keyword argument, `block`, that can be used to specify the number of the block to be used as a context for the estimation.
The default value is `pending` which means that the estimation will be executed in the context of the pending block.

## `access_list` request type

The `access_list` request type is used to estimate the access list and the amount of gas needed to execute a transaction when using the returned access list.
It accepts one more keyword argument, `block`, that can be used to specify the number of the block to be used as a context for the estimation.
The default value is `pending` which means that the estimation will be executed in the context of the pending block.
