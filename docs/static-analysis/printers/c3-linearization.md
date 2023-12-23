# C3 linearization printer

Prints the [C3 linearization](https://docs.soliditylang.org/en/latest/contracts.html#multiple-inheritance-and-linearization) of a contract.

## Example

<div>
--8<-- "docs/static-analysis/printers/c3-linearization.svg"
</div>

## Parameters

| Command-line name | TOML name                 | Type   | Default value | Description                                                              |
|-------------------|---------------------------|--------|---------------|--------------------------------------------------------------------------|
| `--interfaces`    | <nobr>`interfaces`</nobr> | `bool` | `False`       | Whether to include interfaces in the output.                             |
| `--verbose`       | <nobr>`verbose`</nobr>    | `bool` | `False`       | Whether to print more verbose input with base contracts and constructor. |
