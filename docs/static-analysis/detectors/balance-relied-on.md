# Balance relied on detector

Reports uses of `address.balance` in strict equality comparisons and in state variable assignments.

A contract may forcefully receive Ether without a single `payable` function implemented.
This is possible by selfdestructing another contract and sending the Ether to the address of the contract that relies on `address.balance`.

## Example

```solidity hl_lines="17" linenums="1"
pragma solidity ^0.8;

contract Auction {
    address owner;

    constructor() {
        owner = msg.sender;
    }

    receive() external payable {
        // only the owner can start the auction with initial bid
        require(msg.sender == owner);
    }

    function bid() external payable {
        require(
            address(this).balance != 0, // (1)!
            "Cannot bid on an auction that has not started"
        );
        // ...
    }
}
```

1. The contract relies on `address(this).balance` to check if the auction has started.
    An attacker can selfdestruct another contract and send the Ether to the address of the auction contract.
    This will make the auction start and allow the attacker to bid on it.

## Parameters

The detector does not accept any additional parameters.
