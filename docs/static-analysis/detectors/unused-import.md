# Unused import detector

The `unused-import` detector reports import directives that may be removed from the source code.

## Example

```solidity hl_lines="2" linenums="1"
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/utils/Address.sol"; // (1)!

contract MyToken is ERC20 {
    constructor() ERC20("MyToken", "MTK") {
        _mint(msg.sender, 1000000000000000000000000);
    }
}
```

1.  The example source code does not use any symbol from this import directive.

## Parameters

The detector does not accept any additional parameters.