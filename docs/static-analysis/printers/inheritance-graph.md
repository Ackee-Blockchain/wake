# Inheritance graph printer

Generates inheritance graphs of contracts into Graphviz `.dot` files.

## Example

<div class="excalidraw">
--8<-- "docs/static-analysis/printers/inheritance-graph.svg"
</div>

## Parameters

| Command-line name                                                 | TOML name                 | Type                             | Default value              | Description                                                       |
|-------------------------------------------------------------------|---------------------------|----------------------------------|----------------------------|-------------------------------------------------------------------|
| `--name` (multiple)                                               | <nobr>`names`</nobr>      | `List[str]`                      | `[]`                       | Names of contracts to generate inheritance graphs for.            |
| `--out`                                                           | <nobr>`out`</nobr>        | `str`                            | `.wake/inheritance-graphs` | Output directory path.                                            |
| `--direction`                                                     | <nobr>`direction`</nobr>  | Choice of `TB`, `BT`, `LR`, `RL` | `BT`                       | Direction of the graph.                                           |
| `--links`                                                         | <nobr>`links`</nobr>      | `bool`                           | `True`                     | Whether to generate links to the source code.                     |
| `--force`                                                         | <nobr>`force`</nobr>      | `bool`                           | `False`                    | Whether to overwrite existing files.                              |
| `--children`                                                      | <nobr>`children`</nobr>   | `bool`                           | `True`                     | Whether to generate children of selected contracts.               |
| `--parents`                                                       | <nobr>`parents`</nobr>    | `bool`                           | `True`                     | Whether to generate parents of selected contracts.                |
| `--interfaces`                                                    | <nobr>`interfaces`</nobr> | `bool`                           | `True`                     | Whether to generate interfaces.                                   |
| <nobr>`--single-file`</nobr>/<br/><nobr>`--multiple-files`</nobr> | <nobr>`single_file`       | `bool`                           | `True`                     | Whether to generate a single file or multiple files per contract. |
