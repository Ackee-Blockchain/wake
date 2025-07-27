# Invalid memory-safe assembly detector

Name: `invalid-memory-safe-assembly`

Reports usage of `@solidity memory-safe-assembly` in non-NatSpec comments. The Solidity compiler only recognizes memory-safe assembly annotations when they are written in NatSpec format (`///` or `/** */`). Regular comments (`//` or `/* */`) containing this annotation are ignored by the compiler.

## Example

```solidity hl_lines="3 10" linenums="1"
contract Example {
    function badExample() public pure returns (uint256 result) {
        // @solidity memory-safe-assembly (1)
        assembly {
            result := 42
        }
    }

    function anotherBadExample() public pure returns (uint256 result) {
        /* @solidity memory-safe-assembly */  // (2)!
        assembly {
            result := 42
        }
    }

    function goodExample() public pure returns (uint256 result) {
        /// @solidity memory-safe-assembly (3)
        assembly {
            result := 42
        }
    }

    function anotherGoodExample() public pure returns (uint256 result) {
        /** @solidity memory-safe-assembly */  // (4)!
        assembly {
            result := 42
        }
    }
}
```

1. Invalid: Regular `//` comment is ignored by the compiler
2. Invalid: Regular `/* */` comment is ignored by the compiler
3. Valid: NatSpec `///` comment is recognized by the compiler
4. Valid: NatSpec `/** */` comment is recognized by the compiler

## Parameters

The detector does not accept any additional parameters.