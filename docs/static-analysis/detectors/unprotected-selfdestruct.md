# Unprotected selfdestruct detector

Name: `unprotected-selfdestruct`

Reports selfdestruct calls that are not protected by an `onlyOwner` modifier or similar logic.

More precisely, access controls based on `msg.sender` are checked in the detector.
Addresses set in a constructor or in functions protected by `onlyOwner` (or similar) are considered trusted.

## Example

```solidity linenums="1" hl_lines="16"
pragma solidity ^0.8.0;

contract VulnerableSelfDestructExample {
    address public owner;

    constructor() {
        owner = msg.sender;
    }
    
    function safeSelfDestruct() external {
        require(msg.sender == owner, "Only owner can self-destruct");
        selfdestruct(payable(owner)); // (1)!
    }
    
    function unsafeSelfDestruct() external {
        selfdestruct(payable(owner)); // (2)!
    }
}
```

1. The selfdestruct call is protected by a `require` statement and so is not reported.
2. The selfdestruct call is not protected by any access control condition using `msg.sender` and `owner` and so is reported.

## Parameters

The detector does not accept any additional parameters.
