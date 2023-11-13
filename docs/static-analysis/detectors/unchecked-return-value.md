# Unchecked return value detector

Reports when a function call return value is unused.


## Example

```solidity hl_lines="5 9 13" linenums="1"
import "@openzeppelin/contracts/interfaces/IERC20.sol";

contract Treasury {
    function deposit(IERC20 token, uint256 amount) external {
        token.transferFrom(msg.sender, address(this), amount); // (1)!
    }

    function withdrawNative(address to, uint256 amount) external {
        to.call{value: amount}(""); // (2)!
    }
    
    function withdraw(IERC20 token, address to, uint256 amount) external {
        token.transfer(to, amount);  // (3)!
    }
}
```

1. The return value of `transferFrom` is unused, possibly causing logic errors since the transfer may fail.
2. The return value of `call` is unused, silently discarding the boolean indicating whether the call succeeded.
3. The return value of `transfer` is unused, possibly causing logic errors since the transfer may fail.

## Parameters

The detector does not accept any additional parameters.
