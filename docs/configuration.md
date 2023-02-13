# Configuration

Woke can be configured using optional configuration files. The global configuration file is loaded from `$XDG_CONFIG_HOME/woke/config.toml`.
If `$XDG_CONFIG_HOME` is not set, the global configuration file is loaded from:

- `$HOME/.config/woke/config.toml` on Linux/MacOS,
- `%LOCALAPPDATA%\woke\config.toml` on Windows.

Additionally, the configuration file for each project can be located in `{PROJECT_PATH}/woke.toml`.

!!! attention

    Configuration options loaded from TOML files affect only the behavior of the Woke command-line tool.
    LSP configuration options are loaded from LSP clients using the [standard interface](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#workspace_configuration).

## Subconfigs
Any configuration file can include additional configuration files (subconfigs). These subconfigs are loaded after the original configuration file in the specified order. Subconfig configuration values override the values of the parent configuration file.

!!! example "Example woke.toml"
    ```toml
    subconfigs = ["loaded_next.toml", "../relative.toml", "/tmp/absolute.toml", "loaded_last.toml"]
    ```

## Configuration options
The resolution order for each configuration option is:

- default value,
- value in the global configuration file,
- value in the project configuration file.

The latter overrides the former.


???+ info "Default woke.toml"
    Configuration options related to the LSP server are not shown here.
    ```toml
    subconfigs = []

    [compiler.solc]
    allow_paths = []
    # evm_version = "" (unset - let the compiler decide)
    ignore_paths = ["node_modules", ".woke-build", "venv", "lib"]
    include_paths = ["node_modules"]
    remappings = []
    # target_version = "" (unset - use the latest version
    # via_IR = "" (unset - let the compiler decide)

    [compiler.solc.optimizer]
    # enabled = "" (unset - let the compiler decide)
    runs = 200

    [detectors]
    exclude = []
    ignore_paths = ["node_modules", ".woke-build", "venv", "lib"]
    # only = [] (unset - all detectors are enabled)

    [testing]
    cmd = "anvil"
    timeout = 5

    [testing.anvil]
    cmd_args = "--prune-history 100 --base-fee 0 --steps-tracing --silent"

    [testing.ganache]
    cmd_args = "-g 0 -k istanbul -q"

    [testing.hardhat]
    cmd_args = ""
    ```

### `compiler.solc` namespace

| Option                        | Description                                                                                                                                    |
|:------------------------------|:-----------------------------------------------------------------------------------------------------------------------------------------------|
| `allow_paths`                 | Allow paths passed to the `solc` executable                                                                                                    |
| `evm_version`                 | EVM version as specified by the [Solidity docs](https://docs.soliditylang.org/en/latest/using-the-compiler.html#target-options)                |
| `ignore_paths`                | Files in these paths are not compiled unless imported from other non-ignored files                                                             |
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

### `detectors` namespace

| Option         | Description                                                          |
|:---------------|:---------------------------------------------------------------------|
| `exclude`      | List of detector IDs (string or number) that should not be enabled.  |
| `only`         | List of detector IDs (string or number) that should only be enabled. |
| `ignore_paths` | Detections with subdetections in these paths are ignored.            |

### `generator.control_flow_graph` namespace
Related to the `woke.generate.control_flow_graph` LSP command.

| Option        | Description                            | Default value |
|:--------------|:---------------------------------------|:--------------|
| `direction`   | Graph direction                        | `TB`          |
| `vscode_urls` | Attach VS Code URLs to the graph nodes | `true`        |

### `generator.inheritance_graph` namespace
Related to the `woke.generate.inheritance_graph` LSP command.

| Option        | Description                            | Default value |
|:--------------|:---------------------------------------|:--------------|
| `direction`   | Graph direction                        | `BT`          |
| `vscode_urls` | Attach VS Code URLs to the graph nodes | `true`        |

### `generator.inheritance_graph_full` namespace
Related to the `woke.generate.inheritance_graph_full` LSP command.

| Option        | Description                            | Default value |
|:--------------|:---------------------------------------|:--------------|
| `direction`   | Graph direction                        | `BT`          |
| `vscode_urls` | Attach VS Code URLs to the graph nodes | `true`        |

### `generator.linearized_inheritance_graph` namespace
Related to the `woke.generate.linearized_inheritance_graph` LSP command.

| Option        | Description                            | Default value |
|:--------------|:---------------------------------------|:--------------|
| `direction`   | Graph direction                        | `LR`          |
| `vscode_urls` | Attach VS Code URLs to the graph nodes | `true`        |

### `lsp` namespace

| Option              | Description                                                        | Default value |
|:--------------------|:-------------------------------------------------------------------|:--------------|
| `compilation_delay` | Delay in seconds before the project is compiled after a keystroke. | `0`           |

### `lsp.code_lens` namespace

| Option   | Description                            | Default value |
|:---------|:---------------------------------------|:--------------|
| `enable` | Enable LSP code lens language feature. | `true`        |

### `lsp.detectors` namespace

| Option   | Description                                       | Default value |
|:---------|:--------------------------------------------------|:--------------|
| `enable` | Enable vulnerability detectors in the LSP server. | `true`        |

### `lsp.find_references` namespace
Configuration options specific to the LSP `Find references` request.

| Option                 | Description                                                     | Default value |
|:-----------------------|:----------------------------------------------------------------|:--------------|
| `include_declarations` | Also include declarations in `Find references` request results. | `false`       |

### `testing` namespace

| Option    | Description                                                                      |
|:----------|:---------------------------------------------------------------------------------|
| `cmd`     | Development chain implementation to use. May be `anvil`, `hardhat` or `ganache`. |
| `timeout` | Timeout in seconds applied when communicating with the development chain.        |

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
