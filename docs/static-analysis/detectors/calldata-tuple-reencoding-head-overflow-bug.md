# Calldata tuple reencoding head overflow bug detector

Name: `calldata-tuple-reencoding-head-overflow-bug`

Reports a possibility of triggering a compiler bug when ABI-encoding a tuple with at least one dynamic component and the last component as a statically-sized `calldata` array.

The bug would cause malformed output of the ABI encoder caused by overwriting some of the encoded values.
The detector reports concerned ABI-encoding expressions if a fault compiler version may be used.
Functions that when externally called may trigger the bug are also reported. In such cases, the compiler version is not checked since the bug is triggered by the caller.

See the bug [announcement](https://soliditylang.org/blog/2022/08/08/calldata-tuple-reencoding-head-overflow-bug/) for more details.
The bug was fixed in Solidity 0.8.16.

## Example

```solidity hl_lines="9 12" linenums="1"
pragma solidity 0.8.0;

struct T {
    bytes x; // (1)!
    uint[3] y;
}

contract C {
    function f(bool a, T memory b, bytes32[2] memory c) public {} // (2)!

    function vulnerable(bytes32[2] calldata data) external {
        this.f(true, T("abcd", [uint(11), 12, 13]), data); // (3)!
    }
}
```

1. An encoded tuple must have at least one dynamic component. In this example, the dynamic component is `x`.
2. ABI encoding may be explicit (i.e. `abi.encode(...)`) or implicit when doing an external call.
    In this example, the function `f` is called externally. To call the function, its parameters must be ABI-encoded.
    `c` is the last component of the tuple, complying with the condition of statically-sized array.
    `x` in the `T` struct is the dynamic component also needed to trigger the bug.
3. Call to the bug-affected function `f` performs an implicit ABI encoding and triggers the bug.
    `data` must be stored in `calldata` to trigger the bug.

## Parameters

The detector does not accept any additional parameters.
