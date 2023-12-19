# Struct mapping deletion detector

Using `delete` on a (possibly nested) struct containing a mapping member does not delete the mapping.

## Example

```solidity hl_lines="6 12" linenums="1"
pragma solidity 0.8.0;

contract C {
    struct Account {
        string name;
        mapping(uint => uint) balances;  // (2)!
    }

    mapping(uint => Account) accounts;

    function clearAccount(uint id) internal {
        delete accounts[id];  // (1)!
    }
}
```

1. The `delete` statement does not delete the `Account` struct mapping member `balances`.
2. The `balances` member is not deleted.

## Parameters

The detector does not accept any additional parameters.
