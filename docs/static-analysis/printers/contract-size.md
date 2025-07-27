# Contract size printer

Name: `contract-size`

Prints contract bytecode sizes compared to EVM limits for both creation (initcode) and runtime bytecode.

## Example

<div>
--8<-- "docs/static-analysis/printers/contract-size.svg"
</div>

## Parameters

| Command-line name    | TOML name                     | Type        | Default value | Description                                                                          |
|----------------------|-------------------------------|-------------|---------------|--------------------------------------------------------------------------------------|
| `--name` (multiple)  | <nobr>`names`</nobr>          | `List[str]` | `[]`          | Contract names to analyze (can be used multiple times).                              |
| `--all`              | <nobr>`show_all`</nobr>       | `bool`      | `False`       | Include interfaces and libraries (default: contracts only).                         |
| `--details`          | <nobr>`show_details`</nobr>   | `bool`      | `False`       | Show detailed information including full file paths.                                |
| `--files`            | <nobr>`show_files`</nobr>     | `bool`      | `False`       | Show full source unit names.                                                        |
| `--sort-by`          | <nobr>`sort_by`</nobr>        | `str`       | `runtime`     | Sort contracts by: `runtime` size (default), `creation` size, `name`, or `file`.    |