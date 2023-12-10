# Unused modifier detector

Reports unused modifiers.

## Example

```solidity hl_lines="6" linenums="1"
pragma solidity ^0.8;

contract C {
    address public owner;
    
    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner.");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function withdraw() external /*onlyOwner*/ {
        (bool success, ) = msg.sender.call{value: address(this).balance}("");
        require(success, "Transfer failed.");
    }
}
```

## Parameters

The detector does not accept any additional parameters.
