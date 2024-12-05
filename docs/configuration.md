# Configuration

Wake can be configured using configuration options loaded from multiple sources in the following order:

- default values,
- global configuration file,
- project configuration file,
- environment variables,
- command-line arguments.

## Default values

???+ info
    The following TOML snippet shows the default values of all configuration options.
    ```toml
    subconfigs = []

    [api_keys]
    # etherscan = "" (unset - no Etherscan API key)
    # "goerli.etherscan" = "" (unset - no Goerli Etherscan API key)
    # ...

    [compiler.solc]
    allow_paths = []
    # evm_version (unset - let the compiler decide)
    exclude_paths = ["node_modules", "venv", ".venv", "lib", "script", "test"]
    include_paths = ["node_modules"]
    remappings = []
    # target_version (unset - use the latest version)
    # via_IR (unset - let the compiler decide)

    [compiler.solc.optimizer]
    # enabled (unset - let the compiler decide)
    runs = 200

    [compiler.solc.optimizer.details]
    # peephole (unset - let the compiler decide)
    # inliner (unset - let the compiler decide)
    # jumpdest_remover (unset - let the compiler decide)
    # order_literals (unset - let the compiler decide)
    # deduplicate (unset - let the compiler decide)
    # cse (unset - let the compiler decide)
    # constant_optimizer (unset - let the compiler decide)
    # simple_counter_for_loop_unchecked_increment (unset - let the compiler decide)

    [compiler.solc.optimizer.details.yul_details]
    # stack_allocation (unset - let the compiler decide)
    # optimizer_steps (unset - let the compiler decide)

    [deployment]
    confirm_transactions = true
    silent = false

    [detector]

    [detectors]
    exclude = []
    # only (unset - all detectors are enabled)
    ignore_paths = ["venv", ".venv", "test"]
    exclude_paths = ["node_modules", "lib", "script"]

    [printers]
    exclude = []
    # only (unset - all printers are enabled)

    [printer]

    [lsp]
    compilation_delay = 0

    [lsp.code_lens]
    enable = true
    sort_tag_priority = [
        "lsp-references", "lsp-selectors", "lsp-inheritance-graph",
        "lsp-linearized-inheritance-graph"
    ]

    [lsp.detectors]
    enable = true

    [lsp.find_references]
    include_declarations = false

    [lsp.inlay_hints]
    enable = true
    sort_tag_priority = []

    [general]
    call_trace_options = [
        "contract_name", "function_name", "named_arguments", "status",
        "call_type", "value", "return_value", "error", "events"
    ]
    json_rpc_timeout = 15
    link_format = "vscode://file/{path}:{line}:{col}"

    [testing]
    cmd = "anvil"

    [testing.anvil]
    cmd_args = "--prune-history 100 --transaction-block-keeper 10 --steps-tracing --silent"

    [testing.ganache]
    cmd_args = "-k istanbul -q"

    [testing.hardhat]
    cmd_args = ""
    ```

## Global configuration file

The global configuration file is loaded from `$XDG_CONFIG_HOME/wake/config.toml`.
If `$XDG_CONFIG_HOME` is not set, the global configuration file is loaded from:

- `$HOME/.config/wake/config.toml` on Linux/MacOS,
- `%LOCALAPPDATA%\wake\config.toml` on Windows.

Additionally, there is a `plugins.toml` file in the same directory. It holds `verified_paths` with trusted paths to detectors and printers.
The paths are updated automatically with command-line queries or when creating a new detector or printer.

The `plugins.toml` file can be used to specify priorities when having multiple colliding detectors or printers of the same name installed.

!!! example "Example plugins.toml"
    ```toml
    [detector_loading_priorities]
    reentrancy = "my_detectors"  # prefer my_detectors module if present
    unused-import = ["my_detectors", "wake_detectors"]  # prefer my_detectors, then wake_detectors
    "*" = "wake_detectors"  # prefer wake_detectors for all other detectors

    [printer_loading_priorities]
    # follows the same structure
    ```

## Project configuration file

The project configuration file is loaded from `./wake.toml`. This can be changed using the `wake --config path/to/wake.toml` command-line option.

### Subconfigs
The global `config.toml` and project configuration files can include additional TOML files (subconfigs). These subconfigs are loaded after the original configuration file in the specified order. Subconfig configuration values override the values of the parent configuration file.

!!! example
    ```toml
    subconfigs = ["loaded_next.toml", "../relative.toml", "/tmp/absolute.toml", "loaded_last.toml"]
    ```

## Environment variables

Environment variables (if supported) are printed in the help message of each command on the command-line.

## Command-line arguments

Command-line arguments for each command can be displayed using the `--help` option.

## Configuration options

### `api_keys` namespace

The `api_keys` namespace may contain API keys for Etherscan, BscScan, PolygonScan, etc.
Blockchain explorer API keys are stored under the lowercase name of the explorer with a subdomain prefix if needed (e.g. `goerli.etherscan`).

Additionally, detectors and printers may use this namespace to load needed API keys.

!!! warning
    Keep your API keys secret. Store them in the global configuration file or in a separate file included as a subconfig and add this file to `.gitignore`.

### `compiler.solc` namespace

| Option                        | Description                                                                                                                                    |
|:------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------|
| `allow_paths`                 | Allow paths passed to the `solc` executable                                                                                                    |
| `evm_version`                 | EVM version as specified by the [Solidity docs](https://docs.soliditylang.org/en/latest/using-the-compiler.html#target-options)                |
| `exclude_paths`               | Files in these paths are not compiled unless imported from other non-excluded files                                                            |
| <nobr>`include_paths`</nobr>  | Paths (along with the current working directory) where files from non-relative imports are searched                                            |
| `remappings`                  | Compiler remappings as specified by the [Solidity docs](https://docs.soliditylang.org/en/latest/path-resolution.html#import-remapping)         |
| <nobr>`target_version`</nobr> | Target `solc` version used to compile the project                                                                                              |
| `via_IR`                      | Compile the code via the Yul intermediate language (see the [Solidity docs](https://docs.soliditylang.org/en/latest/ir-breaking-changes.html)) |

!!! info
    The `include_paths` option is the preferred way to handle imports of libraries. Remappings should be used only when `include_paths` cannot be used (e.g. when the import path differs from the system path of the imported file).

### `compiler.solc.optimizer` namespace

| Option    | Description                                                                                                                                                                                                                                                        |
|:----------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `enabled` | Compile the project with solc optimizations enabled. Leaving this unset disables most of the available optimizations. Setting this to `false` disables all optimizations for Solidity <0.8.6 and has the same behavior as leaving this unset for Solidity >=0.8.6. |
| `runs`    | Configuration of the optimizer specifying how many times the code is intended to be run. Lower values optimize more for initial deployment cost, while higher values optimize more for high-frequency usage.                                                       |

### `compiler.solc.optimizer.details` namespace

For optimizer details, see the [Solidity docs](https://docs.soliditylang.org/en/latest/using-the-compiler.html#input-description). Settings follow the same structure as in the Solidity docs with an exception of `optimizer.details.yul` not being supported.

### `detector` namespace

This namespace contains detector-specific configuration options. See the documentation of each detector for more information.
Each detector has its own namespace under the `detector` namespace, e.g. `detector.reentrancy`.
Every detector supports at least the `min_confidence` and `min_impact` options:

!!! example
    ```toml
    [detector."unchecked-return-value"]
    min_confidence = "medium"
    min_impact = "high"
    ```

### `detectors` namespace

| Option                       | Description                                                                                                                      |
|:-----------------------------|:---------------------------------------------------------------------------------------------------------------------------------|
| `exclude`                    | List of detectors that should not be enabled.                                                                                    |
| `only`                       | List of detectors that should only be enabled.                                                                                   |
| <nobr>`ignore_paths`</nobr>  | Detections or subdetections in these paths are always ignored. Intended for files that will never be deployed (e.g. test files). |
| <nobr>`exclude_paths`</nobr> | Detections are excluded if a whole detection (including subdetections) is in these paths. Intended for dependencies.             |

### `general` namespace

| Option                            | Description                                                                                                                                                                                                          |
|:----------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| <nobr>`call_trace_options`</nobr> | What information to display in call traces. Possible options: `contract_name`, `address`, `function_name`, `named_arguments`, `arguments`, `status`, `call_type`, `value`, `gas`, `sender`, `return_value`, `error`, `events`. |
| `json_rpc_timeout`                | Timeout in seconds when communicating with a node via JSON-RPC.                                                                                                                                                      |
| `link_format`                     | Format of links to source code files used in detectors and printers. The link should contain `{path}`, `{line}` and `{col}` placeholders.                                                                            |

### `generator.control_flow_graph` namespace
Related to the `wake.generate.control_flow_graph` LSP command.

| Option        | Description                                                | Default value |
|:--------------|:-----------------------------------------------------------|:--------------|
| `direction`   | Graph direction. Possible options: `TB`, `BT`, `LR`, `RL`. | `TB`          |
| `vscode_urls` | Attach VS Code URLs to the graph nodes                     | `true`        |

### `generator.imports_graph` namespace
Related to the `wake.generate.imports_graph` LSP command.

| Option                           | Description                                                                                                    | Default value           |
|:---------------------------------|:---------------------------------------------------------------------------------------------------------------|:------------------------|
| `direction`                      | Graph direction. Possible options: `TB`, `BT`, `LR`, `RL`.                                                     | `TB`                    |
| <nobr>`imports_direction`</nobr> | Direction of edges between imported files. Possible options: `imported-to-importing`, `importing-to-imported`. | `imported-to-importing` |
| `vscode_urls`                    | Attach VS Code URLs to the graph nodes                                                                         | `true`                  |

### `generator.inheritance_graph` namespace
Related to the `wake.generate.inheritance_graph` LSP command.

| Option        | Description                                                | Default value |
|:--------------|:-----------------------------------------------------------|:--------------|
| `direction`   | Graph direction. Possible options: `TB`, `BT`, `LR`, `RL`. | `BT`          |
| `vscode_urls` | Attach VS Code URLs to the graph nodes                     | `true`        |

### `generator.inheritance_graph_full` namespace
Related to the `wake.generate.inheritance_graph_full` LSP command.

| Option        | Description                                                | Default value |
|:--------------|:-----------------------------------------------------------|:--------------|
| `direction`   | Graph direction. Possible options: `TB`, `BT`, `LR`, `RL`. | `BT`          |
| `vscode_urls` | Attach VS Code URLs to the graph nodes                     | `true`        |

### `generator.linearized_inheritance_graph` namespace
Related to the `wake.generate.linearized_inheritance_graph` LSP command.

| Option        | Description                                                | Default value |
|:--------------|:-----------------------------------------------------------|:--------------|
| `direction`   | Graph direction. Possible options: `TB`, `BT`, `LR`, `RL`. | `LR`          |
| `vscode_urls` | Attach VS Code URLs to the graph nodes                     | `true`        |

### `lsp` namespace

| Option                           | Description                                                        |
|:---------------------------------|:-------------------------------------------------------------------|
| <nobr>`compilation_delay`</nobr> | Delay in seconds before the project is compiled after a keystroke. |

### `lsp.code_lens` namespace

| Option                           | Description                                                                                                                                            |
|:---------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------|
| `enable`                         | Enable LSP code lens language server feature.                                                                                                          |
| <nobr>`sort_tag_priority`</nobr> | Order of code lens with the same start and end position based on sort tags used in detectors/printers. Sort tags default to the printer/detector name. |

### `lsp.detectors` namespace

| Option   | Description                                       |
|:---------|:--------------------------------------------------|
| `enable` | Enable vulnerability detectors in the LSP server. |

### `lsp.find_references` namespace
Configuration options specific to the LSP `Find references` request.

| Option                              | Description                                                     |
|:------------------------------------|:----------------------------------------------------------------|
| <nobr>`include_declarations`</nobr> | Also include declarations in `Find references` request results. |

### `lsp.inlay_hints` namespace

| Option                           | Description                                                                                                                                |
|:---------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------|
| `enable`                         | Enable inlay hints language server feature.                                                                                                |
| <nobr>`sort_tag_priority`</nobr> | Order of inlay hints with the same position based on sort tags used in detectors/printers. Sort tags default to the printer/detector name. |

### `printer` namespace

This namespace contains printer-specific configuration options. See the documentation of each printer for more information.
Each printer has its own namespace under the `printer` namespace, e.g. `printer."lsp-references"`.

!!! example
    ```toml
    [printer."lsp-references"]
    local_variables = false
    ```

### `printers` namespace

The following settings mainly apply to LSP printers that are run automatically by the LSP server.

| Option                       | Description                                   |
|:-----------------------------|:----------------------------------------------|
| `exclude`                    | List of printers that should not be enabled.  |
| `only`                       | List of printers that should only be enabled. |

### `testing` namespace

| Option    | Description                                                                      |
|:----------|:---------------------------------------------------------------------------------|
| `cmd`     | Development chain implementation to use. May be `anvil`, `hardhat` or `ganache`. |

### `testing.anvil` namespace

| Option     | Description                                                                |
|:-----------|:---------------------------------------------------------------------------|
| `cmd_args` | Command line arguments passed to the `anvil` executable when launching it. |

### `testing.ganache` namespace

| Option     | Description                                                                  |
|:-----------|:-----------------------------------------------------------------------------|
| `cmd_args` | Command line arguments passed to the `ganache` executable when launching it. |

### `testing.hardhat` namespace

| Option     | Description                                                                        |
|:-----------|:-----------------------------------------------------------------------------------|
| `cmd_args` | Command line arguments passed to the `npx hardhat node` command when launching it. |
