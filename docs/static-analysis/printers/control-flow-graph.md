# Control flow graph printer

Generates control flow graphs of functions and modifiers into Graphviz `.dot` files.

## Example

<div class="excalidraw">
--8<-- "docs/static-analysis/printers/control-flow-graph.svg"
</div>

## Parameters

| Command-line name   | TOML name                | Type                             | Default value               | Description                                                           |
|---------------------|--------------------------|----------------------------------|-----------------------------|-----------------------------------------------------------------------|
| `--name` (multiple) | <nobr>`names`</nobr>     | `List[str]`                      | `[]`                        | Names of functions and modifiers to generate control flow graphs for. |
| `--out`             | <nobr>`out`</nobr>       | `str`                            | `.wake/control-flow-graphs` | Output directory path.                                                |
| `--direction`       | <nobr>`direction`</nobr> | Choice of `TB`, `BT`, `LR`, `RL` | `TB`                        | Direction of the graph.                                               |
| `--links`           | <nobr>`links`</nobr>     | `bool`                           | `True`                      | Whether to generate links to the source code.                         |
| `--force`           | <nobr>`force`</nobr>     | `bool`                           | `False`                     | Whether to overwrite existing files.                                  |
