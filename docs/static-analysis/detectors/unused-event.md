# Unused event detector

Name: `unused-event`

Reports events that are not used in the source code.

## Example

```solidity hl_lines="2" linenums="1"
contract C {
    event WithdrawalCompleted(address indexed user, uint256 amount);  // (1)!

    function withdraw() public {
        (bool success, ) = msg.sender.call{value: address(this).balance}("");
        require(success, "Transfer failed.");
    }
}
```

1. This event is never emitted.

## Parameters

The detector does not accept any additional parameters.
