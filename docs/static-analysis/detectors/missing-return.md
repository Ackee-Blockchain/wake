# Missing return detector

Reports functions that contain at least one execution path that does not set all return variables.

## Example

```solidity hl_lines="4" linenums="1"
pragma solidity ^0.8;

contract C {
    function sqrt(uint x) public returns (uint) { // (1)!
        if (x >= 2) {
            uint z = (x + 1) / 2;
            uint y = x;
            while (z < y) {
                y = z;
                z = (x / z + z) / 2;
            }
            return y;
        }
    }
}
```

1. The function does not set the return value if `x < 2`. This is a problem since `sqrt(1)` will return `0` instead of `1`.

## Parameters

The detector does not accept any additional parameters.
