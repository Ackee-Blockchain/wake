# Storage layout printer

Prints storage layout of contracts in given paths or in the whole project.

## Example

<div>
--8<-- "docs/static-analysis/printers/storage-layout.svg"
</div>

## Parameters

| Command-line name | TOML name                   | Type   | Default value | Description                                                                         |
|-------------------|-----------------------------|--------|---------------|-------------------------------------------------------------------------------------|
| `--split-slots`   | <nobr>`split_slots`</nobr>  | `bool` | `False`       | Print a horizontal line between different slots.                                    |
| `--table-style`   | <nobr>`table_style`</nobr>  | `str`  | `""`          | [Rich style](https://rich.readthedocs.io/en/stable/style.html) of the table.        |
| `--header-style`  | <nobr>`header_style`</nobr> | `str`  | `""`          | [Rich style](https://rich.readthedocs.io/en/stable/style.html) of the table header. |
| `--style`         | <nobr>`style`</nobr>        | `str`  | `cyan`        | [Rich style](https://rich.readthedocs.io/en/stable/style.html) of the table cells.  |
