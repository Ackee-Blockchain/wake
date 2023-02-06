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

Abi.decode(['uint8', 'address'], b'\xff\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
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
It accepts a deployer (`Account`, `Address` or a hex string address), a salt and the contract deployment code.

```python
from woke.testing import Account, get_create2_address_from_code
from woke.testing.fuzzing import random_bytes
from pytypes.contracts.Counter import Counter

get_create2_address_from_code(
    Account(1),
    random_bytes(32),
    Counter.deployment_code()
)
```

### get_create2_address_from_hash

`get_create2_address_from_hash` computes the address of a contract deployed using the `CREATE2` opcode.
It accepts a deployer (`Account`, `Address` or a hex string address), a salt and the hash of the contract deployment code.

```python
from woke.testing import Account, get_create2_address_from_hash, keccak256
from woke.testing.fuzzing import random_bytes
from pytypes.contracts.Counter import Counter

get_create2_address_from_hash(
    Account(1),
    random_bytes(32),
    keccak256(Counter.deployment_code())
)
```
