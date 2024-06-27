# Troubleshooting

## `UnknownTransactionRevertedError(data=b'')`

In many different cases, a development chain or compiler auto-generated code does not provide any useful information about the revert reason.
This section describes the most common cases and how to debug them.

### ABI decoding error

Failed ABI decoding reverts without reason data. The decoding can be explicit (e.g. `abi.decode(data, (uint256))`) or implicit when performing an external call, for example:

```solidity
contract Reverting {
    uint256 public immutable initialTotalSupply;

    constructor(address token) {
        initialTotalSupply = IERC20(token).totalSupply();
    }
}
```

To debug the latter case, print the call trace of the failing transaction. The trace should contain the failing call in a malformed way.

```python
from wake.testing import *
from pytypes.contracts.Reverting import Reverting


def revert_handler(e: TransactionRevertedError):
    if e.tx is not None:
        print(e.tx.call_trace)


@chain.connect()
@on_revert(revert_handler)
def test_reverting():
    r = Reverting.deploy(Address("0x9a6A6920008318b3556702b5115680E048c2c8dB"))
```

<div>
--8<-- "docs/images/testing/reverting-call-trace.svg"
</div>

### Contract code size limit

The Spurious Dragon hard fork introduced a limit on the size of a contract. The limit is 24,576 bytes of bytecode.
Due to the limit, a deployment transaction may fail with the `UnknownTransactionRevertedError` error without any reason data.
In this case, the transaction call trace **does not contain any red cross**, but the transaction itself still fails.

To debug this error, compile the project and search for a warning message similar to the following:

```
Warning: Contract code size exceeds 24576 bytes (a limit introduced in Spurious Dragon). This contract may not be deployable on mainnet.
Consider enabling the optimizer (with a low "runs" value!), turning off revert strings, or using libraries.
```

### Invalid opcode

When EVM encounters an invalid opcode, it reverts without any reason data.
Under normal circumstances, an invalid opcode should never be encountered unless explicitly triggered by the contract code.

However, the `PUSH0` opcode may behave as invalid if the chain is not configured for the Shanghai hard fork or later.
To debug this issue, try to set a different pre-Shanghai EVM version in the Wake config file.

```yaml
[compiler.solc]
evm_version = "paris"
```

## `WebSocketTimeoutException`

### Insufficient timeout configured

Occasionally, the default timeout may be insufficient, especially when performing complex transactions or when fork testing.

To work around this issue, increase the timeout in the Wake config file.

```toml
[general]
json_rpc_timeout = 60
```

## Test freezes without timeout error

### Contract initcode size limit

Due to faulty implementations of development chains, a test may freeze without any error message. Especially, a **timeout error is not raised**.
The reason may be that the transaction is trying to deploy a contract with initcode larger than the limit introduced in the Shanghai hard fork.

To debug this issue, compile the project and search for a warning message similar to the following:

```
Warning: Contract initcode size is 151670 bytes and exceeds 49152 bytes (a limit introduced in Shanghai).
This contract may not be deployable on Mainnet. Consider enabling the optimizer (with a low "runs" value!), turning off revert strings, or using libraries.
```