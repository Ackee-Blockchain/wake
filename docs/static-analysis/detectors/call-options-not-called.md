# Call options not called detector

Reports when a function call option (`gas`, `salt` or `value`) is used but the corresponding function is not called.
Both old-style syntax `:::solidity .value(...)` and new-style syntax `:::solidity {value: ...}` are supported.

## Example

```solidity linenums="1" hl_lines="5 9"
pragma solidity ^0.6.0;

contract Example {
    function withdraw() external {
        msg.sender.call{value: address(this).balance}; // (1)!
    }

    function withdraw2() external {
        msg.sender.call.value(address(this).balance); // (2)!
    }
}
```

1. The `value` call option is used but the low-level `call` function is not called.
2. The `value` call option is used but the low-level `call` function is not called.

## Parameters

The detector does not accept any additional parameters.