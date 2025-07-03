# ABI printer

Name: `abi`

Prints ABI of contracts in given paths or in the whole project.

## Example

<div>
--8<-- "docs/static-analysis/printers/abi.svg"
</div>

## Parameters

| Command-line name             | TOML name                   | Type        | Default value                             | Description                                                                            |
|-------------------------------|-----------------------------|-------------|-------------------------------------------|----------------------------------------------------------------------------------------|
| `--name` (multiple)           | <nobr>`names`</nobr>        | `List[str]` | `[]`                                      | Names of contracts to print ABI for.                                                   |
| `--out`                       | `out`                       | `str`       | `abi` if `--out` passed, `None` otherwise | Output directory path. If not specified, the output is printed to the standard output. |
| <nobr>`--skip-empty`</nobr>   | <nobr>`skip_empty`</nobr>   | `bool`      | `False`                                   | Skip contracts with empty ABI.                                                         |
| <nobr>`--keep-folders`</nobr> | <nobr>`keep_folders`</nobr> | `bool`      | `False`                                   | Preserve the original folder hierarchy when exporting ABIs to output directory.        |
