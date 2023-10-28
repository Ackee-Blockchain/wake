# Accounts and addresses

Wake testing framework strictly distinguishes between accounts and addresses.
However, in most cases, API functions accept both `Account` and `Address` types.

## Addresses

`Address` is a 20-byte value encoded as a hex string. It can be constructed from
a hex string or an integer:

```python
from wake.testing import Address

Address("0x0000000000000000000000000000000000000000")
Address(0)
```

The hex string does not have to be [EIP-55](https://eips.ethereum.org/EIPS/eip-55) compliant.

Addresses can be compared with each other:

```python
from wake.testing import Address

assert Address(1) > Address(0)
```

## Accounts

`Account` is an `Address` bound to a specific `Chain`. It can be constructed from
an `Address`, a hex string or an integer. Optionally, a chain can be specified, otherwise
the `default_chain` global object is used:

```python
from wake.testing import Account, Chain, default_chain

other_chain = Chain()

assert Account(0) == Account(0, default_chain)
assert Account(0) != Account(0, other_chain)
```

`Address` and `Account` instances cannot be compared with each other. `Account` instances belonging to different
chains cannot be compared using the `<` and `>` operators.

!!! warning "Using accounts belonging to different chains"
    To save users from accidentally using accounts belonging to different chains, Wake testing framework
    does not accept `Account` instances belonging to different chains in most API functions. To overcome
    this limitation, it is possible to use the `address` property of an `Account` instance.

### Importing accounts and addresses

`Account` and `Address` instances can be imported from a private key:

```python
from wake.testing import Account, Address

Account.from_key("0x" + "a" * 64)
Address.from_key("0x" + "a" * 64)
```

From a mnemonic:

```python
from wake.testing import Account, Address

Account.from_mnemonic(" ".join(["test"] * 11 + ["junk"]))
Address.from_mnemonic(" ".join(["test"] * 11 + ["junk"]))
```

Or from an alias (see [Managing accounts with private keys](./deployment.md#managing-accounts-with-private-keys)):

```python
from wake.testing import Account, Address

Account.from_alias("alice")
Address.from_alias("alice")
```

It is also possible to create a new account with a random private key:

```python
from wake.testing import Account

Account.new()
```

In all of the above cases, a private key is stored together with the account and can be used to sign transactions or messages.

### Signing messages

`Account` instances can be used to sign messages. This is only possible if the account has a known private key.
The private key must be imported using one of the methods described in the previous section or must be owned by
the client (the account must be present in `chain.accounts`).

#### Signing raw messages

Using `account.sign(message)` it is possible to sign any message in the form of bytes:

```python
from wake.testing import Account

account = Account.from_mnemonic(" ".join(["test"] * 11 + ["junk"]))
signature = account.sign(b"Hello, world!")
```

The message is signed according to the [EIP-191](https://eips.ethereum.org/EIPS/eip-191) standard (version `0x45`).

#### Signing structured messages

Using `account.sign_structured(message)` it is possible to sign structured messages.

```python
from wake.testing import *
from dataclasses import dataclass


@dataclass
class Transfer:
    sender: Address
    recipient: Address
    amount: uint256


account = Account.from_mnemonic(" ".join(["test"] * 11 + ["junk"]))
signature = account.sign_structured(
    Transfer(
        sender=account.address,
        recipient=Address(1),
        amount=10,
    ),
    domain=Eip712Domain(
        name="Test",
        chainId=default_chain.chain_id,
    )
)
```

See [EIP-712](https://eips.ethereum.org/EIPS/eip-712) for more information.

#### Signing message hash

While it is not recommended to sign message hashes directly, it is sometimes necessary.
To sign a message hash, use `account.sign_hash(message_hash)`.

```python
from wake.testing import *

account = Account.from_mnemonic(" ".join(["test"] * 11 + ["junk"]))
signature = account.sign_hash(keccak256(b"Hello, world!"))
```

!!! note
    `account.sign_hash` is not available for accounts owned by the client.

!!! warning
    Always sign a message hash only if you know the original message.

### Assigning labels

`Account` instances can be assigned labels. Labels override the default string representation
of the account:

```python
from wake.testing import Account

account = Account(0)
account.label = "ZERO"
```

Setting the label to `None` removes the label.

### Account properties

`Account` instances have the following properties:

| Property      | Description                           |
|---------------|---------------------------------------|
| `address`     | `Address` of the account              |
| `balance`     | balance of the account in Wei         |
| `chain`       | `Chain` the account is bound to       |
| `code`        | code of the account                   |
| `label`       | string label of the account           |
| `nonce`       | nonce of the account                  |
| `private_key` | private key of the account (if known) |

Except for `address`, `chain` and `private_key`, all properties can be assigned to. `nonce` can only be incremented.

### Low-level calls and transactions

Each `Account` instance has `call`, `transact`, `estimate` and `access_list` methods that can be used to perform arbitrary
requests (see [Interacting with contracts](./interacting-with-contracts.md)).

```python
from wake.testing import *


@default_chain.connect()
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

## Contract accounts

Contract accounts are accounts that have non-empty code. Everything that applies to `Account` instances
also applies to contract accounts. However, contract accounts have additional methods:

- `get_creation_code` - returns the code used to deploy the contract, may require addresses of libraries needed by the contract,
- `deploy` - deploys the contract, requires equivalent arguments as the constructor of the contract in Solidity,
- other contract-specific methods generated in `pytypes`, including getters for public state variables.

```python
from pytypes.contracts.Counter import Counter

assert len(Counter.get_creation_code()) > 0
print(Counter.setCount.selector.hex())
```

Every method of a contract generated in `pytypes` has a `selector` property.

!!! tip "Constructing contracts from an address"
    The ability to construct a contract from an address (and an optional `Chain` instance) can be very useful
    when interacting with contracts through proxies:

    ```python
    from wake.testing import *
    from pytypes.contracts.Counter import Counter
    from pytypes.openzeppelin.contracts.proxy.ERC1967.ERC1967Proxy import ERC1967Proxy

    @default_chain.connect()
    def test_proxy():
        default_chain.default_tx_account = default_chain.accounts[0]

        impl = Counter.deploy()
        proxy = ERC1967Proxy.deploy(impl, b"")

        # behave as if Counter was deployed at proxy.address
        counter = Counter(proxy.address)
        counter.increment()
        assert counter.count() == 1
    ```
