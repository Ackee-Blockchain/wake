# Reentrancy detector

Reports calls to external contracts that may allow reentrancy attacks.
The vulnerability is only reported if there is at least one public/external function in the contract that can be called
by anyone, serving as an entry point for the reentrancy attack. The entry points are reported as subdetections.

A function is considered to be an entry point if it does not have any access control checks in a form of `msg.sender == trustedAddress`,
where `trustedAddress` is an address set only in the constructor of the contract or in a function protected by the same access control check.

A reentrancy detection is not reported if an externally called contract is considered to be trusted. The same rules apply
here - the external call address must only be assigned to by the deployer of the contract in the constructor or an access
control protected function.

The impact of a detection depends on the EVM global state changes that are performed after the external call.
For example, if the external call is only followed by an event emission, the impact is evaluated as warning.
Still, it may be an issue if there is any backend logic that relies on the correct order of events.

## Example

```solidity hl_lines="12" linenums="1"
pragma solidity ^0.8.0;

contract Reentrancy {
    mapping(address => uint256) public balances;

    function deposit() public payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw(uint256 amount) public {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        (bool success, ) = msg.sender.call{value: amount}(""); // (1)!
        require(success, "Transfer failed");
        balances[msg.sender] -= amount;
    }
}
```

1. The contract calls `msg.sender.call` before updating the balance of the user.
   This allows the user to call `withdraw` again before the balance is updated,
   withdrawing more funds than they have deposited.

## Parameters

The detector does not accept any additional parameters.
