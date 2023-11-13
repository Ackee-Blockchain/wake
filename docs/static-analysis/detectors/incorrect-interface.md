# Incorrect interface detector

Reports multiple different issues when implementing [ERC-20](https://eips.ethereum.org/EIPS/eip-20)/[ERC-721](https://eips.ethereum.org/EIPS/eip-721)/[ERC-1155](https://eips.ethereum.org/EIPS/eip-1155) interfaces.

## Missing functions & events

One or more functions or events are missing from the contract. The recognition is based on the function/event selectors.

### Example

```solidity hl_lines="3" linenums="1"
pragma solidity ^0.8;

contract MyToken { // (1)!
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);

    function approve(address spender, uint256 value) external returns (bool) {
        // ...
    }
    
    function transfer(address to, uint256 value) external returns (bool) {
        // ...
    }
}
```

1. The contract does not implement the `transferFrom` function and the `Approval` event defined in the [ERC20](https://eips.ethereum.org/EIPS/eip-20) standard.

## Incorrect state mutability

Some functions are marked as `view` in the token standards as they are not supposed to modify the state.
The detector reports functions that should be marked as `view` but are not.

### Example

```solidity hl_lines="12" linenums="1"
pragma solidity ^0.8;

contract MyToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(
        address indexed owner, address indexed spender, uint256 value
    );
    
    function totalSupply() external returns (uint256) { // (1)!
        // ...
    }
    
    function approve(address spender, uint256 value) external returns (bool) {
        // ...
    }
    
    function transfer(address to, uint256 value) external returns (bool) {
        // ...
    }
    
    function transferFrom(
        address from, address to, uint256 value
    ) external returns (bool) {
        // ...
    }
}
```

1. The `totalSupply` function should be marked as `pure` or `view`, but it is not.

## Incorrect return type

Return types do not affect the function selectors. Still, tokens implemented according to the standard should return values as specified in the standard.

### Example

```solidity hl_lines="13 17 23" linenums="1"
pragma solidity ^0.8;

contract MyToken {
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    
    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(
        address indexed owner, address indexed spender, uint256 value
    );

    function approve(address spender, uint256 value) external { // (1)!
        // ...
    }

    function transfer(address to, uint256 value) external { // (2)!
        // ...
    }
    
    function transferFrom(
        address from, address to, uint256 value
    ) external { // (3)!
        // ...
    }
}
```

1. The `approve` function should return a `bool` value, but it does not.
2. The `transfer` function should return a `bool` value, but it does not.
3. The `transferFrom` function should return a `bool` value, but it does not.

## Indexed event parameters

Indexed event parameters do not affect the event selectors, but they still should be used according to the standard.

### Example

```solidity hl_lines="8 12" linenums="1"
pragma solidity ^0.8;

contract MyToken {
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    
    event Transfer(address indexed from, address to, uint256 value); // (1)!
    event Approval(
        address indexed owner,
        address indexed spender,
        uint256 indexed value // (2)!
    );
    
    function approve(address spender, uint256 value) external returns (bool) {
        // ...
    }
    
    function transfer(address to, uint256 value) external returns (bool) {
        // ...
    }
    
    function transferFrom(
        address from, address to, uint256 value
    ) external returns (bool) {
        // ...
    }
}
```

1. The `to` parameter of the `Transfer` event should be indexed, but it is not.
2. The `value` parameter of the `Approval` event should not be indexed, but it is.

## Anonymous events

Events defined in the token standards should not be anonymous.

### Example

```solidity hl_lines="10" linenums="1"
pragma solidity ^0.8;

contract MyToken {
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    
    event Transfer(
        address indexed from, address indexed to, uint256 value
    ) anonymous; // (1)!
    event Approval(
        address indexed owner, address indexed spender, uint256 value
    );
    
    function approve(address spender, uint256 value) external returns (bool) {
        // ...
    }
    
    function transfer(address to, uint256 value) external returns (bool) {
        // ...
    }
    
    function transferFrom(
        address from, address to, uint256 value
    ) external returns (bool) {
        // ...
    }
}
```

1. The `Transfer` event should not be anonymous, but it is.

## Parameters

| Command-line name                  | TOML name                        | Type  | Default value | Description                                                                            |
|------------------------------------|----------------------------------|-------|---------------|----------------------------------------------------------------------------------------|
| <nobr>`--erc20-threshold`</nobr>   | <nobr>`erc20_threshold`</nobr>   | `int` | `4`           | Number of ERC-20 functions/events required to consider a contract an ERC-20 token.     |
| <nobr>`--erc721-threshold`</nobr>  | <nobr>`erc721_threshold`</nobr>  | `int` | `6`           | Number of ERC-721 functions/events required to consider a contract an ERC-721 token.   |
| <nobr>`--erc1155-threshold`</nobr> | <nobr>`erc1155_threshold`</nobr> | `int` | `4`           | Number of ERC-1155 functions/events required to consider a contract an ERC-1155 token. |
