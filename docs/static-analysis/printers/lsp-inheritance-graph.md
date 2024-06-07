# LSP inheritance graph

Name: `lsp-inheritance-graph`

Generates an inheritance graph of a contract by clicking on the code lens using the Language Server Protocol.

## Example

![LSP inheritance graph example](./lsp-inheritance-graph.gif)

## Parameters

| TOML name   | Type                             | Default value | Description                                   |
|-------------|----------------------------------|---------------|-----------------------------------------------|
| `direction` | Choice of `TB`, `BT`, `LR`, `RL` | `BT`          | Direction of the graph.                       |
| `urls`      | `bool`                           | `true`        | Whether to generate links to the source code. |
