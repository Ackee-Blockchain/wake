# `msg.value` non-payable function

Name: `msg-value-nonpayable-function`

Reports uses of `msg.value` in functions that are never called from a payable function.
The value of `msg.value` is always zero in such functions.

## Example

```solidity hl_lines="9" linenums="1"
pragma solidity ^0.8;

contract C {
    function f() public {
        g();
    }

    function g() private {
        require(msg.value > 0); // (1)!
        // ...
    }
}
```

1. The function `g` is never called from a payable function in this example.
   The value of `msg.value` will always be zero.

## Parameters

The detector does not accept any additional parameters.
