# Helper functions

Woke testing framework provides a set of helper functions to make testing easier.

## ABI encoding and decoding

The `Abi` class provides functions to encode and decode data according to the ABI specification.

### Abi.encode

`Abi.encode` encodes a list of values given a list of types. It returns `bytes`:

```python
from woke.testing import Abi, Address

Abi.encode(['uint8', 'address'], [0xff, Address(0)])
```

### Abi.encode_packed

`Abi.encode_packed` encodes a list of values given a list of types. It returns `bytes`:

```python
from woke.testing import Abi

Abi.encode_packed(['bytes', 'string'], [b'abc', 'def'])
```

### Abi.encode_with_selector

`Abi.encode_with_selector` encodes a list of values and a selector given a list of types and the selector. It returns `bytes`:

```python
from woke.testing import Abi
from pytypes.contracts.Counter import Counter

Abi.encode_with_selector(Counter.setCount.selector, ['uint256'], [0xff])
```

### Abi.encode_with_signature

`Abi.encode_with_signature` encodes a list of values and a selector given a list of types and a signature. It returns `bytes`:

```python
from woke.testing import Abi

Abi.encode_with_signature("setCount(uint256)", ['uint256'], [0xff])
```

!!! warning
    The signature string must conform to the [ABI specification](https://docs.soliditylang.org/en/latest/abi-spec.html#function-selector).
    The common mistakes are:
    
    - `uint` or `int` used instead of `uint256` or `int256`,
    - return type specified,
    - spaces in the signature string.

### Abi.encode_call

`Abi.encode_call` encodes a list of values and a selector given a reference to a function. It returns `bytes`:

```python
from woke.testing import Abi
from pytypes.contracts.Counter import Counter

Abi.encode_call(Counter.setCount, [0xff])
```

### Abi.decode

`Abi.decode` decodes a `bytes` object given a list of types. It returns a list of values:

```python
from woke.testing import Abi

Abi.decode(['uint8', 'address'], b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
```

## Keccak-256

The `keccak256` function computes the Keccak-256 hash of a `bytes` object:

```python
from woke.testing import keccak256

keccak256(b'abc')
```

## Computing `CREATE` and `CREATE2` address

In some cases, it may be useful to compute the address of a contract before it is deployed. Woke testing framework provides three functions to do so.

### get_create_address

`get_create_address` computes the address of a contract deployed in a transaction or in a contract using the `CREATE` opcode.
It accepts a deployer (`Account`, `Address` or a hex string address) and its nonce.

```python
from woke.testing import Account, get_create_address

deployer = Account(1)
get_create_address(deployer, deployer.nonce)
```

### get_create2_address_from_code

`get_create2_address_from_code` computes the address of a contract deployed using the `CREATE2` opcode.
It accepts a deployer (`Account`, `Address` or a hex string address), a salt and the contract creation code.

```python
from woke.testing import Account, get_create2_address_from_code
from woke.testing.fuzzing import random_bytes
from pytypes.contracts.Counter import Counter

get_create2_address_from_code(
    Account(1),
    random_bytes(32),
    Counter.get_creation_code()
)
```

### get_create2_address_from_hash

`get_create2_address_from_hash` computes the address of a contract deployed using the `CREATE2` opcode.
It accepts a deployer (`Account`, `Address` or a hex string address), a salt and the hash of the contract creation code.

```python
from woke.testing import Account, get_create2_address_from_hash, keccak256
from woke.testing.fuzzing import random_bytes
from pytypes.contracts.Counter import Counter

get_create2_address_from_hash(
    Account(1),
    random_bytes(32),
    keccak256(Counter.get_creation_code())
)
```

## Get logic contract from proxy

`get_logic_contract` returns the logic contract `Account` from a proxy `Account`.
If the input account is not a proxy, it returns the input account.

```python
from woke.testing import Account, get_logic_contract

usdc_proxy = Account("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
usdc_logic = get_logic_contract(usdc_proxy)
```

## Read & write storage variable

`read_storage_variable` and `write_storage_variable` read and write storage variables of a contract.
They accept a contract `Account` and a variable name. Reading and writing whole arrays, structs and mappings currently is not supported.
Instead, the `keys` argument must be used to provide a list of all keys (array and mapping indices, struct member names) needed to access the variable.

If the provided contract is a proxy, the variable definition is searched in the logic contract and the proxy storage is used.
This behavior can be overridden by setting the `storage_layout_contract` argument.
In this case, the variable definition is searched in the provided `storage_layout_contract`.

```python
from woke.testing import Account, Address, read_storage_variable, write_storage_variable

usdc_proxy = Account("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
write_storage_variable(usdc_proxy, "balances", 1000, keys=[Address(1)])
assert read_storage_variable(usdc_proxy, "balances", keys=[Address(1)]) == 1000
```

## ERC-20 mint and burn

`mint_erc20` and `burn_erc20` mint and burn ERC-20 tokens. They detect the `totalSupply` and `balances` variables using heuristics and may not work for all contracts.
Optionally, `balance_slot` and `total_supply_slot` arguments can be used to specify the storage slot where the balance of the given account and the total supply are stored.

```python
from woke.testing import Account, mint_erc20, burn_erc20
from pytypes.contracts.IERC20 import IERC20

usdc_proxy = IERC20("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
burn_erc20(usdc_proxy, Account(1), usdc_proxy.balanceOf(Account(1)))
mint_erc20(usdc_proxy, Account(1), 1000)
assert usdc_proxy.balanceOf(Account(1)) == 1000
```

## Decorators

### on_revert

`on_revert` is a decorator that simplifies handling of revert exceptions. It accepts a callback function that will be called if the decorated function reverts.

```python
from woke.testing import *

def revert_handler(e: TransactionRevertedError):
    if e.tx is not None:
        print(e.tx.call_trace)
        print(e.tx.console_logs)

@default_chain.connect()
@on_revert(revert_handler)
def test_reverts():
    ...
```
