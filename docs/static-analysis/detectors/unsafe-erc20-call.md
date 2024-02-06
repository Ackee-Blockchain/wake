# Unsafe ERC-20 call detector

Reports ERC-20 `approve`, `transfer`, and `transferFrom` calls.
These calls are unsafe as some non-compliant ERC-20 tokens may revert on failure instead of returning `false`.
On success, the token may not return any data causing an ABI decoding error.

## Example

```solidity hl_lines="3 7 16" linenums="1"
contract C {
    function withdraw(IERC20 token, uint amount) external {
        token.transfer(msg.sender, amount);
    }

    function approve(IERC20 token, address spender, uint amount) external {
        token.approve(spender, amount);
    }

    function transferFrom(
        IERC20 token,
        address sender,
        address recipient,
        uint amount
    ) external {
        token.transferFrom(sender, recipient, amount);
    }
}
```

## Parameters

The detector does not accept any additional parameters.
