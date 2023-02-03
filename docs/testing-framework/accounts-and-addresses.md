# Accounts and addresses

Woke testing framework strictly distinguishes between accounts and addresses.
However, in most cases, API functions accept both `Account` and `Address` types.

## Addresses

`Address` is a 20-byte value encoded as a hex string. It can be constructed from
a hex string or an integer:

```python
from woke.testing import Address

Address("0x0000000000000000000000000000000000000000")
Address(0)
```

The hex string does not have to be [EIP-55](https://eips.ethereum.org/EIPS/eip-55) compliant.

Addresses can be compared with each other:

```python
from woke.testing import Address

assert Address(1) > Address(0)
```

## Accounts

`Account` is an `Address` bound to a specific `Chain`. It can be constructed from
an `Address`, a hex string or an integer. Optionally, a chain can be specified, otherwise
the `default_chain` global object is used:

```python
from woke.testing import Account, Chain, default_chain

other_chain = Chain()

assert Account(0) == Account(0, default_chain)
assert Account(0) != Account(0, other_chain)
```

`Address` and `Account` instances cannot be compared with each other. `Account` instances belonging to different
chains cannot be compared using the `<` and `>` operators.

!!! warning "Using accounts belonging to different chains"
    To save users from accidentally using accounts belonging to different chains, Woke testing framework
    does not accept `Account` instances belonging to different chains in most API functions. To overcome
    this limitation, it is possible to use the `address` property of an `Account` instance.

### Assigning labels

`Account` instances can be assigned labels. Labels override the default string representation
of the account:

```python
from woke.testing import Account

account = Account(0)
account.label = "ZERO"
```

Setting the label to `None` removes the label.

### Account properties

`Account` instances have the following properties:

| Property  | Description                     |
|-----------|---------------------------------|
| `address` | `Address` of the account        |
| `chain`   | `Chain` the account is bound to |
| `label`   | string label of the account     |
| `balance` | balance of the account in Wei   |
| `code`    | code of the account             |
| `nonce`   | nonce of the account            |

Except for `address` and `chain`, all properties can be assigned to. `nonce` can only be incremented.

### Low-level calls and transactions

Each `Account` instance has `call` and `transact` methods that can be used to perform arbitrary
calls and transactions (see [Interacting with a contract](basic-usage.md#interacting-with-a-contract)).
Both methods accept `data`, `value`, `from_` and `gas_limit` keyword arguments. The `transact` method
additionaly accepts the `return_tx` keyword argument.

```python
from woke.testing import *

@connect(default_chain)
def test_accounts():
    alice = default_chain.accounts[0]
    bob = default_chain.accounts[1]

    alice.balance = 100
    bob.balance = 0

    bob.transact(value=10, from_=alice)
    assert alice.balance == 90
    assert bob.balance == 10
```

The previous example shows how to transfer Wei from one account to another.

!!! tip "Encoding data for low-level calls and transactions"
    To prepare the `data` payload, the `Abi` helper class can be used. It offers the same ABI encoding
    functions as the `abi` global object in Solidity.

    ```python
    from woke.testing import *
    from pytypes.contracts.Counter import Counter

    @connect(default_chain)
    def test_low_level_transact():
        default_chain.default_tx_account = default_chain.accounts[0]

        counter = Counter.deploy()

        # execute counter.setCount(100) using a low-level transaction
        counter.transact(data=Abi.encode_call(Counter.setCount, [100]))
        assert counter.count() == 100
    ```
    
## Contract accounts

Contract accounts are accounts that have non-empty code. Everything that applies to `Account` instances
also applies to contract accounts. However, contract accounts have additional methods:

- `deployment_code` - returns the code used to deploy the contract, may require addresses of libraries needed by the contract,
- `deploy` - deploys the contract, requires equivalent arguments as the constructor of the contract in Solidity,
- other contract-specific methods generated in `pytypes`, including getters for public state variables.

```python
from pytypes.contracts.Counter import Counter

assert len(Counter.deployment_code()) > 0
print(Counter.setCount.selector.hex())
```

Every method of a contract generated in `pytypes` has a `selector` property.

!!! tip "Constructing contracts from an address"
    The ability to construct a contract from an address (and an optional `Chain` instance) can be very useful
    when interacting with contracts through proxies:

    ```python
    from woke.testing import *
    from pytypes.contracts.Counter import Counter
    from pytypes.openzeppelin.contracts.proxy.ERC1967.ERC1967Proxy import ERC1967Proxy

    @connect(default_chain)
    def test_proxy():
        default_chain.default_tx_account = default_chain.accounts[0]

        impl = Counter.deploy()
        proxy = ERC1967Proxy.deploy(impl, b"")

        # behave as if Counter was deployed at proxy.address
        counter = Counter(proxy.address)
        counter.increment()
        assert counter.count() == 1
    ```
