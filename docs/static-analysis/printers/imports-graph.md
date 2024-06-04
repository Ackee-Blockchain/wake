# Imports graph printer

Name: `imports-graph`

Generates an imports graph of Solidity source files into a Graphviz `.dot` file.

## Example

<div class="excalidraw">
--8<-- "docs/static-analysis/printers/imports-graph.svg"
</div>

## Parameters

| Command-line name                                             | TOML name                      | Type                                                       | Default value              | Description                                                |
|---------------------------------------------------------------|--------------------------------|------------------------------------------------------------|----------------------------|------------------------------------------------------------|
| `--out`                                                       | <nobr>`out`</nobr>             | `str`                                                      | `.wake/imports-graphs.dot` | Output file path.                                          |
| `--graph-direction`                                           | <nobr>`graph_direction`</nobr> | Choice of `TB`, `BT`, `LR`, `RL`                           | `TB`                       | Direction of the graph.                                    |
| `--edge-direction`                                            | <nobr>`edge_direction`</nobr>  | Choice of `imported-to-importing`, `importing-to-imported` | `imported-to-importing`    | Direction of the edges.                                    |
| `--links`                                                     | <nobr>`links`</nobr>           | `bool`                                                     | `True`                     | Whether to generate links to the source code.              |
| `--force`                                                     | <nobr>`force`</nobr>           | `bool`                                                     | `False`                    | Whether to overwrite existing files.                       |
| <nobr>`--importers`</nobr>/<br/><nobr>`--no-importers`</nobr> | <nobr>`importers`</nobr>       | `bool`                                                     | `True`                     | Whether to generate files importing the specified files.   |
| <nobr>`--imported`</nobr>/<br/><nobr>`--no-imported`</nobr>   | <nobr>`imported`</nobr>        | `bool`                                                     | `True`                     | Whether to generate files imported by the specified files. |
