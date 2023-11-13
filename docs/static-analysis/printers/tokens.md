# Tokens printer

The printer prints the list of all [ERC-20](https://eips.ethereum.org/EIPS/eip-20), [ERC-721](https://eips.ethereum.org/EIPS/eip-721), and [ERC-1155](https://eips.ethereum.org/EIPS/eip-1155) tokens detected in the analyzed contracts.

## Example

<div>
--8<-- "docs/static-analysis/printers/tokens.svg"
</div>

## Parameters

| Command-line name                                        | TOML name                        | Type   | Default value | Description                                                                            |
|----------------------------------------------------------|----------------------------------|--------|---------------|----------------------------------------------------------------------------------------|
| `--erc20`                                                | <nobr>`erc20`</nobr>             | `bool` | `True`        | Print ERC-20 tokens.                                                                   |
| `--erc721`                                               | <nobr>`erc721`</nobr>            | `bool` | `True`        | Print ERC-721 tokens.                                                                  |
| `--erc1155`                                              | <nobr>`erc1155`</nobr>           | `bool` | `True`        | Print ERC-1155 tokens.                                                                 |
| `--erc20-threshold`                                      | <nobr>`erc20_threshold`</nobr>   | `int`  | `4`           | Number of ERC-20 functions/events required to consider a contract an ERC-20 token.     |
| `--erc721-threshold`                                     | <nobr>`erc721_threshold`</nobr>  | `int`  | `6`           | Number of ERC-721 functions/events required to consider a contract an ERC-721 token.   |
| `--erc1155-threshold`                                    | <nobr>`erc1155_threshold`</nobr> | `int`  | `4`           | Number of ERC-1155 functions/events required to consider a contract an ERC-1155 token. |
| <nobr>`--interface`</nobr>/<nobr>`--no-interface`</nobr> | <nobr>`interface`</nobr>         | `bool` | `False`       | Print interfaces.                                                                      |
| <nobr>`--abstract`</nobr>/<nobr>`--no-abstract`</nobr>   | <nobr>`abstract`</nobr>          | `bool` | `False`       | Print abstract contracts.                                                              |
| `--table-style`                                          | <nobr>`table_style`</nobr>       | `str`  | `""`          | [Rich style](https://rich.readthedocs.io/en/stable/style.html) of the table.           |
| `--header-style`                                         | <nobr>`header_style`</nobr>      | `str`  | `""`          | [Rich style](https://rich.readthedocs.io/en/stable/style.html) of the table header.    |
| `--style`                                                | <nobr>`style`</nobr>             | `str`  | `cyan`        | [Rich style](https://rich.readthedocs.io/en/stable/style.html) of the table cells.     |
