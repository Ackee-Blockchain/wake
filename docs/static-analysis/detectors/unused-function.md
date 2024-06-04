# Unused function detector

Name: `unused-function`

Reports private and internal functions that are not used in the source code.

## Example

```solidity hl_lines="2" linenums="1"
contract C {
    function _withdraw() private {
        (bool success, ) = msg.sender.call{value: address(this).balance}("");
        require(success, "Transfer failed.");
    }
}
```

## Parameters

The detector does not accept any additional parameters.
