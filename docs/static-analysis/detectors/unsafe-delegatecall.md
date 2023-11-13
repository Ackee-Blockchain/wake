# Unsafe delegatecall detector

The `unsafe-delegatecall` detector reports `delegatecall` calls to possibly untrusted contracts.

Calls are ignored if they the `delegatecall` target is trusted (e.g. `this`) or if the call is protected by an `onlyOwner` modifier or similar logic.

More precisely, access controls based on `msg.sender` are checked in the detector.
Addresses set in a constructor or in functions protected by `onlyOwner` (or similar) are considered trusted.

## Example

```solidity hl_lines="22-24" linenums="1"
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/interfaces/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

contract Storage {
    using SafeERC20 for IERC20;

    mapping(address => uint256) public balances;
    address public computationLogic;

    function setComputationLogic(address _computationLogic) external {
        computationLogic = _computationLogic;
    }

    function deposit(IERC20 token, uint256 amount) external {
        token.safeTransferFrom(msg.sender, address(this), amount);
        balances[msg.sender] += amount;
    }

    function recomputeRewards() external {
        computationLogic.delegatecall(
            abi.encodeWithSignature("recomputeRewards()")
        ); // (1)!
    }
}
```

1. The `delegatecall` call is not protected by any access control condition using `msg.sender` and `owner`. The `computationLogic` variable can be set by anyone, making it possible to call arbitrary code that can modify the storage of the `Storage` contract.

## Parameters

| Command-line name                 | TOML name | Type   | Default value | Description                                                |
|-----------------------------------|-----------|--------|---------------|------------------------------------------------------------|
| <nobr>`--proxy/--no-proxy`</nobr> | `proxy`   | `bool` | `false`       | Whether to report `delegatecall` calls in proxy contracts. |
