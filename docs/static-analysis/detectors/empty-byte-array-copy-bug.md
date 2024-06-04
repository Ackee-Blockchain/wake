# Empty byte array copy bug detector

Name: `empty-byte-array-copy-bug`

Reports a possibility of triggering a compiler bug when copying empty `calldata` or `memory` bytes to `storage` bytes and then extending the `storage` bytes using `.push()`.
See the bug [announcement](https://soliditylang.org/blog/2020/10/19/empty-byte-array-copy-bug/) for more details.
The bug was fixed in Solidity 0.7.4.

## Example

```solidity hl_lines="11" linenums="1"
pragma solidity ^0.7;

contract Example {
    bytes public data;

    function foo() external {
        bytes memory empty;
        uint[2] memory arr;
        arr[0] = type(uint).max;
        data = empty; // (1)!
        data.push(); // (2)!
    }
}
```

1. Empty `memory` bytes are copied to `storage` bytes.
2. The `storage` bytes are extended using `.push()`. Because of the compiler bug, a non-zero byte is possibly appended to the `storage` bytes.

## Parameters

The detector does not accept any additional parameters.
