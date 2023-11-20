# Solidity LSP server
Wake implements an [LSP](https://microsoft.github.io/language-server-protocol/) server for Solidity. The only currently supported communication channel is TCP.

Wake LSP server can be run using:
```shell
wake lsp
```

Or with an optional `--port` argument (default 65432):
```shell
wake lsp --port 1234
```

!!! info

    Multi-root workspaces are not currently supported.

## Projects using Wake LSP server
- [VS Code Extension](https://marketplace.visualstudio.com/items?itemName=AckeeBlockchain.tools-for-solidity)

## Configuration options
Server configuration options are loaded using the [standard interface](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#workspace_configuration) from LSP clients. The process of setting the configuration options is client specific. Configuration changes are handled by the server, and the project is recompiled if the compilation options change.

The full list of supported configuration options can be found in the [configuration](configuration.md#configuration-options) section.

!!! tip
    The LSP server automatically loads the configuration options from the `wake.toml` file located in the root of the project if `wake.use_toml_if_present` is set to `True`.

    The path to the configuration file can be changed using the `wake.toml_path` configuration option.

## Supported commands

Wake LSP server implements the command execution provider as specified by the [LSP specification](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#workspace_executeCommand). The following commands are supported:

| Command                                                   | Arguments                                                                                                                                                                                  | Description                                                                                                                                     |
|:----------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------|
| <nobr>`wake.init.detector`</nobr>                         | `0`: name of the detector<br>`1`: boolean indicating whether the detector should be global (True) or project-specific (False)                                                              | Initialize a detector from a template in `$XDG_DATA_HOME/wake/global-detectors` or `./detectors` (if the detector is project-specific).         |
| <nobr>`wake.init.printer`</nobr>                          | `0`: name of the printer<br>`1`: boolean indicating whether the printer should be global (True) or project-specific (False)                                                                | Initialize a printer from a template in `$XDG_DATA_HOME/wake/global-printers` or `./printers` (if the printer is project-specific).             |
| <nobr>`wake.lsp.force_recompile`</nobr>                   |                                                                                                                                                                                            | Force recompile the opened project/files. Useful after modifying files outside the IDE (e.g. after installing npm packages).                    |
| <nobr>`wake.lsp.force_rerun_detectors`</nobr>             |                                                                                                                                                                                            | Force rerun detectors on the opened project/files.                                                                                              |
| <nobr>`wake.generate.control_flow_graph`</nobr>           | `0`: [URI](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#uri) of the document containing the function<br>`1`: canonical name of the function | Generate a control flow graph for the given function or modifier. Returns the source code of the graph in Graphviz (DOT) format.                |
| <nobr>`wake.generate.imports_graph`</nobr>                |                                                                                                                                                                                            | Generate an imports graph for the whole project. A workspace must be opened. Returns the source code of the graph in Graphviz (DOT) format.     |
| <nobr>`wake.generate.inheritance_graph`</nobr>            | `0`: [URI](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#uri) of the document containing the contract<br>`1`: name of the contract           | Generate an inheritance graph for the given contract. Returns the source code of the graph in Graphviz (DOT) format.                            |
| <nobr>`wake.generate.inheritance_graph_full`</nobr>       |                                                                                                                                                                                            | Generate an inheritance graph for the whole project. A workspace must be opened. Returns the source code of the graph in Graphviz (DOT) format. |
| <nobr>`wake.generate.linearized_inheritance_graph`</nobr> | `0`: [URI](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#uri) of the document containing the contract<br>`1`: name of the contract           | Generate a linearized inheritance graph for the given contract. Returns the source code of the graph in Graphviz (DOT) format.                  |

## Features

### Go to definition

![Go to definition preview](images/lsp/go-to-definition.gif)

### Go to type definition

![Go to type definition preview](images/lsp/go-to-type-definition.gif)

### Go to implementation

Finds implementations of an unimplemented function or modifier.

![Go to implementation preview](images/lsp/go-to-implementation.gif)

### Find references

![Find references preview](images/lsp/find-references.gif)

### Type hierarchy

![Contract type hierarchy preview](images/lsp/contract-type-hierarchy.gif)

Also works for virtual functions.

![Function type hierarchy preview](images/lsp/function-type-hierarchy.gif)

### Document links

![Document links preview](images/lsp/document-links.gif)

### Hover

Includes links to documentation for OpenZeppelin contracts.

![Hover preview](images/lsp/hover.gif)

### Code lens

Number of references is shown above each declaration.

![Code lens preview](images/lsp/code-lens.png)

### Document symbols

![Document symbols preview](images/lsp/document-symbols.png)

### Diagnostics

![Diagnostics preview](images/lsp/diagnostics-1.gif)

![Diagnostics preview](images/lsp/diagnostics-2.png)

Together with compiler errors, diagnostics also include results from Wake vulnerability detectors.

![Diagnostics preview](images/lsp/diagnostics-3.png)

![Diagnostics preview](images/lsp/diagnostics-4.png)

### Rename

![Rename preview](images/lsp/rename.gif)

## Debugging

Wake LSP server can be debugged using:
```shell
wake --debug lsp
```
