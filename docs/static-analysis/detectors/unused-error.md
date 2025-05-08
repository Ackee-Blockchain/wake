# Unused error detector

Name: `unused-error`

Reports user-defined errors that are not used in the source code.

## Example

```solidity hl_lines="2" linenums="1"
contract C {
    error TransferFailed();  // (1)!

    function withdraw() public {
        (bool success, ) = msg.sender.call{value: address(this).balance}("");
        require(success, "Transfer failed.");
    }
}
```

1. This error is never used.

## Parameters

The detector does not accept any additional parameters.
