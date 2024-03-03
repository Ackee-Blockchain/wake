# Compilation

Wake comes with default compilation settings that should work for many projects.
However, in some cases, it may be necessary to customize the compilation settings.

To run the compiler, use:
```sh
wake compile
```

The `--help` flag can be used to display additional options.

!!! tip
    Wake comes with `wake up` (to initialize a new or existing project) and `wake up config` (to prepare just the `wake.toml` config file) commands.
    The commands can automatically set remappings for Foundry projects and enable the solc optimizer if needed.

## Include paths

Include paths define locations where to search for Solidity files imported using direct (non-relative) import strings.
An example of a direct import string is:
```solidity
import "openzeppelin/contracts/token/ERC20/ERC20.sol";
```

The default settings for include paths are:
```toml title="wake.toml"
[compiler.solc]
include_paths = ["node_modules"]
```

!!! info
    Include paths should only be used if path segments (directories in the import string) reflect directories in the file system.

    For example, if the import string is `import "openzeppelin/contracts/token/ERC20/ERC20.sol";`, but the file is located at `node_modules/openzeppelin/src/contracts/token/ERC20/ERC20.sol`, then include paths cannot be used because of the `src` directory in the path.

## Remappings

Remappings allow performing a substitution in import strings. More information about remappings can be found in the [Solidity documentation](https://docs.soliditylang.org/en/latest/path-resolution.html#import-remapping).

!!! note
    It is highly recommended to use include paths instead of remappings whenever possible.

### Foundry projects

Include paths typically cannot be used in Foundry projects. The `forge remappings` command can generate remappings that can be copied into the `wake.toml` file:
```console
$ forge remappings
@openzeppelin/contracts-upgradeable/=lib/openzeppelin-contracts-upgradeable/contracts/
@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/
ds-test/=lib/forge-std/lib/ds-test/src/
forge-std/=lib/forge-std/src/
```

```toml title="wake.toml"
[compiler.solc]
remappings = [
  "@openzeppelin/contracts-upgradeable/=lib/openzeppelin-contracts-upgradeable/contracts/",
  "@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/",
  "ds-test/=lib/forge-std/lib/ds-test/src/",
  "forge-std/=lib/forge-std/src/"
]
```

## Exclude paths

Exclude paths define locations of Solidity files that should not be compiled unless imported from another non-excluded file.

The default settings for exclude paths are:
```toml title="wake.toml"
[compiler.solc]
exclude_paths = ["node_modules", "venv", ".venv", "lib", "script", "test"]
```

## Via IR

The compiler can can generate bytecode by converting the sources to Yul first (`Solidity -> Yul -> EVM bytecode`) instead of the traditional `Solidity -> EVM bytecode` approach.
See the [Solidity documentation]() for more information.

By default, the `via_IR` config option is left unset, which leaves the decision to the compiler.
It can be enabled by setting the option to `true`:
```toml title="wake.toml"
[compiler.solc]
via_IR = true
```

!!! note "`Stack too deep` errors"
    One way to avoid `Stack too deep` errors is to enable `via_IR` and the optimizer.

## Optimizer

Wake allows setting all optimizer options supported by the Solidity compiler (see the [Solidity documentation](https://docs.soliditylang.org/en/v0.8.22/using-the-compiler.html#input-description)).
By default, Wake leaves the `enabled` option unset, which leaves the decision to the compiler.
It can be enabled by setting the option to `true`:
```toml title="wake.toml"
[compiler.solc.optimizer]
enabled = true
runs = 200
```
