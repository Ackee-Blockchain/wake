# `tx.origin` detector

Name: `tx-origin`

## Phishing attacks

Access controls based on `tx.origin` are vulnerable to phishing attacks. The
attacker may convince the user to send a transaction to an attacker's contract.
The attacker's contract may then call the victim's contract with `tx.origin` set
to the victim's address.

### Example

```solidity linenums="1" hl_lines="11"
pragma solidity ^0.8.0;

contract Victim {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function withdraw() {
        require(tx.origin == owner, "Not owner"); // (1)!
        tx.origin.call{value: this.balance}("");
    }
}
```

1. An attacker may convince `owner` to send a transaction to the attacker's
   contract. `tx.origin` will be set to `owner`. Attacker's contract calls
    `withdraw` on the victim's contract, withdrawing the victim's funds.

## Account abstraction

Use of `tx.origin` may prevent users using [ERC-4337](https://www.erc4337.io/) account abstraction from interacting with a contract.
In this case, `tx.origin` will not be set to the address of the user operation sender.

### Example

```solidity linenums="1" hl_lines="7"
pragma solidity ^0.8.0;

contract Treasury {
    mapping(address => uint256) public deposits;

    function deposit() public payable {
        require(tx.origin == msg.sender, "Only EOAs can deposit"); // (1)!
        deposits[msg.sender] += msg.value;
    }
}
```

1. Users using account abstraction will not be able to deposit funds into the
   contract.

## Parameters


| Command-line name                                       | TOML name                          | Type   | Default value | Description                                                                    |
|---------------------------------------------------------|------------------------------------|--------|---------------|--------------------------------------------------------------------------------|
| `--account-abstraction/`<br/>`--no-account-abstraction` | <nobr>`account_abstraction`</nobr> | `bool` | `true`        | Report [ERC-4337](https://www.erc4337.io/) account abstraction related issues. |