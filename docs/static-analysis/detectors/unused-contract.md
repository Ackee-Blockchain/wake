# Unused contract detector

Reports abstract contracts, interfaces, and libraries that are not used in the source code.

## Example

```solidity hl_lines="1 5 9" linenums="1"
abstract contract A { // (1)!
    function foo() external virtual;
}

interface I { // (2)!
    function bar() external;
}

library L { // (3)!
    function baz() external {}
}

contract C {
    function qux() external {}
}
```

1. The abstract contract `A` is not used in the source code.
2. The interface `I` is not used in the source code.
3. The library `L` is not used in the source code.

## Parameters

| Command-line name                         | TOML name   | Type   | Default value | Description                                  |
|-------------------------------------------|-------------|--------|---------------|----------------------------------------------|
| <nobr>`--abstract/--no-abstract`</nobr>   | `abstract`  | `bool` | `true`        | Whether to report unused abstract contracts. |
| <nobr>`--interface/--no-interface`</nobr> | `interface` | `bool` | `true`        | Whether to report unused interfaces.         |
| <nobr>`--library/--no-library`</nobr>     | `library`   | `bool` | `true`        | Whether to report unused libraries.          |
