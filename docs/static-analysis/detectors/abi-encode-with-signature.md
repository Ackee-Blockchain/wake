# `abi.encodeWithSignature` detector

The detector checks for incorrect ABI signatures in `ABI.encodeWithSignature` calls.
The most common mistake is the use of `uint` instead of `uint256` or `int` instead of `int256`.

## Examples

```solidity hl_lines="6" linenums="1"
import "@openzeppelin/contracts/interfaces/IERC20.sol";

contract Example {
    function transfer(IERC20 token, uint amount) external {
        bytes memory data = abi.encodeWithSignature(
            "transfer(address,uint)", // (1)!
            msg.sender,
            amount
        );
        (bool success, ) = address(token).call(data);
        require(success, "Transfer failed");
    }
}
```

1. `uint256` must be used instead of `uint` to generate the correct function selector.

## Parameters

The detector does not accept any additional parameters.
