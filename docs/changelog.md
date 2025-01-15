# Changelog

<style>
small.label {
    color: var(--md-primary-fg-color);
}
</style>

## 4.14.0 <small>(Jan 15, 2025)</small> { id="4.14.0" }

Features & improvements:

- [Sourcify](https://sourcify.dev/) is now used as alternative to Etherscan-like explorers as a source code provider <small class="label">[core]</small>
- Wake now connects to any Ethereum node, assuming Geth-like interface <small class="label">[deployment framework]</small>
- introduced Cookbook section in docs <small class="label">[docs]</small>
- `link_format` is now used in all LSP printers and commands <small class="label">[language server]</small>
- added new JSON-HTML detections export format <small class="label">[static analysis]</small>
- improved bytes representation in call traces and deployment tx confirmations <small class="label">[testing & deployment framework]</small>
- added events to call traces <small class="label">[testing & deployment framework]</small>
- introduced experimental fuzz test crash shrinking feature <small class="label">[testing framework]</small>
- added `mint_erc1155` cheatcode <small class="label">[testing framework]</small>

Changes:

- removed unmaintained `no-pytest` testing mode <small class="label">[testing framework]</small>

Fixes:

- fixed SIGINT behavior in single-process testing <small class="label">[testing framework]</small>


## 4.13.2 <small>(Nov 14, 2024)</small> { id="4.13.2" }

Fixes:

- fixed coverage collection in multiprocess testing <small class="label">[testing framework]</small>

## 4.13.1 <small>(Nov 4, 2024)</small> { id="4.13.1" }

Fixes:

- fixed non-deterministic pytypes generation for source files under multiple different source unit names <small class="label">[testing & deployment framework]</small>
- fixed pytypes generation for source units with dots in their names <small class="label">[testing & deployment framework]</small>
- fixed `tx` not assigned on error that could not be resolved <small class="label">[testing & deployment framework]</small>
- fixed latest supported tx type not properly detected with Anvil caused by breaking change in Anvil <small class="label">[testing framework]</small>
- fixed base fee parsing with Anvil caused by breaking change in Anvil <small class="label">[testing framework]</small>

## 4.13.0 <small>(Oct 14, 2024)</small> { id="4.13.0" }

Features & improvements:

- added support for Solidity 0.8.28 <small class="label">[core]</small>
- Github is now used as a secondary source of solc binaries <small class="label">[core]</small>
- added support for compilation metadata settings <small class="label">[core]</small>
- optimized compilation with `solc` >= 0.8.28 on CLI <small class="label">[core]</small>

Fixes:

- fixed language server crash on editing files removed on disk but still opened in IDE <small class="label">[language server]</small>
- fixed compilation of Etherscan contracts <small class="label">[testing framework]</small>

## 4.12.1 <small>(Oct 7, 2024)</small> { id="4.12.1" }

Fixes & improvements:

- fixed removal of errored files from compilation build <small class="label">[core]</small>
- fixed AST node indexing of multiple structurally different ASTs <small class="label">[core]</small>
- fixed crashes on non-utf8 files present in workspace on compilation <small class="label">[core]</small>
- increased timeouts for solc binary installation <small class="label">[core]</small>
- fixed LSP features not available for files without workspace <small class="label">[language server]</small>
- improved error logging of LSP subprocesses <small class="label">[language server]</small>
- Anvil is now also being searched in standard `~/.foundry/bin` directory <small class="label">[testing framework]</small>

## 4.12.0 <small>(Oct 2, 2024)</small> { id="4.12.0" }

Features & improvements:

- added support for Solidity 0.8.27 <small class="label">[core]</small>
- implemented `wake compile` and `wake detect` JSON export <small class="label">[core]</small>
- introduced support for subprojects compilation <small class="label">[core]</small>
- added initial support for LSP 3.18 specification <small class="label">[language server]</small>
- injected `wake_random_seed` variable into debugger instances <small class="label">[testing framework]</small>
- transaction revert and EVM halt errors are now properly distinguished with Anvil <small class="label">[testing framework]</small>

Fixes:

- fixed `wake detect` detection code snippets trailing blank lines <small class="label">[core]</small>
- fixed Deploy & Interact compilation of contracts without provided bytecode <small class="label">[language server]</small>
- `KeyboardInterrupt` is now handled correctly in multiprocess testing <small class="label">[testing framework]</small>
- `breakpoint` is now supported in multiprocess testing <small class="label">[testing framework]</small>

## 4.11.1 <small>(Aug 26, 2024)</small> { id="4.11.1" }

Changes:

- Wake now does not scan for Solidity files in hidden directories both in CLI and LSP <small class="label">[core]</small>

Fixes:

- fixed exception when accessing `Assignment.assigned_variables` for array access with base enclosed in parentheses <small class="label">[core]</small>
- fixed indexing of Solidity AST compiled with both >=0.8 and <0.8 versions with AST node represented by `IdentifierPath` in >=0.8 and `Identifier` in <0.8 <small class="label">[core]</small>
- fixed memory not always available in call traces in LSP contract deployment & interaction <small class="label">[language server]</small>
- fixed `FileNotFoundError` when scanning for Solidity files in LSP <small class="label">[language server]</small>

## 4.11.0 <small>(Aug 13, 2024)</small> { id="4.11.0" }

Features & improvements:

- improved merging of compilation units in context of min. supported version and target version set in config <small class="label">[core]</small>
- CLI does not raise exception on compilation of files with Solidity version lower than min. supported version <small class="label">[core]</small>
- Wake IR now uses weak references to avoid cyclic references preventing garbage collection <small class="label">[core]</small>
- improved error messages when Rosetta is not enabled on macOS <small class="label">[core]</small>
- added optional `--incremental` CLI option to `wake up` commands <small class="label">[core]</small>
- introduced API for deployment & interaction with Solidity contracts through LSP <small class="label">[language server]</small>
- language server now watches for external changes to Solidity files (e.g. through git branch switch) and recompiles automatically <small class="label">[language server]</small>
- improved language server RAM usage <small class="label">[language server]</small>
- improved language server responsiveness, especially when recompiling <small class="label">[language server]</small>
- improved multiprocessing test status messages <small class="label">[testing framework]</small>

Fixes:

- added `certifi` dependency on macOS - should resolve SSL certificates error when downloading solc binaries <small class="label">[core]</small>
- fixed imported source unit removed from build artifacts while importing source unit kept in build artifacts <small class="label">[core]</small>
- fixed variable name location parsing when variable has empty name <small class="label">[core]</small>
- fixed sending compilation build to detectors/printers subprocess causing crashes due to build size & cyclic references <small class="label">[language server]</small>
- fixed multiple memory leaks in LSP <small class="label">[language server]</small>
- fixed LSP `mcopy` definition - thanks to @madlabman <small class="label">[language server]</small>
- fixed language server crashes due to unexpected code action kinds <small class="label">[language server]</small>
- fixed race conditions when creating language server context and initialising server <small class="label">[language server]</small>
- fixed LSP watchdog URI format causing crashes in Neovim <small class="label">[language server]</small>
- fixed multiple other LSP compilation bugs <small class="label">[language server]</small>
- fixed max. supported tx type detection with DRPC node <small class="label">[deployment framework]</small>
- fixed `.selector` types in pytypes (`bytes4` and `bytes32` instead of `bytes`) <small class="label">[testing & deployment framework]</small>

## 4.10.1 <small>(Jun 11, 2024)</small> { id="4.10.1" }

Fixes:

- fixed language server unicode decoding crash when trying to read from non-existent files <small class="label">[language server]</small>
- fixed Yul definitions of `shl`, `shr` and `sar` instructions in `lsp-yul-definitions` printer <small class="label">[language server]</small>
- fixed handling of language server subprocess crashes <small class="label">[language server]</small>

## 4.10.0 <small>(Jun 11, 2024)</small> { id="4.10.0" }

Features & improvements:

- implemented abi encoding & decoding of errors <small class="label">[testing framework]</small>
- included standard Solidity interfaces, Create3 deployer and ERC-1967 factory into bundled-in contracts <small class="label">[testing framework]</small>
- detectors & printers now run in subprocesses in LSP <small class="label">[language server]</small>
- implemented LSP workspace symbols feature <small class="label">[language server]</small>
- added support for Solidity 0.8.26 <small class="label">[core]</small>
- implemented `exclude` and `only` config options for printers <small class="label">[core]</small>

Changes:

- improved `random_int` documentation & incorrect value checking <small class="label">[testing framework]</small>
- changed `__str__` and `__repr__` of `Account` for easier debugging <small class="label">[testing framework]</small>
- code lens LSP features re-implemented as LSP printers + created docs <small class="label">[language server]</small>
- dropped support for Python 3.7 <small class="label">[core]</small>
- upgraded pydantic to 2.x <small class="label">[core]</small>

Fixes:

- fixed pickling error when encoding dataclasses using new abi encoder <small class="label">[testing framework]</small>
- fixed file descriptors leak in LSP <small class="label">[language server]</small>
- fixed misbehavior of LSP configuration key removal <small class="label">[language server]</small>
- fixed LSP connection crash due to incorrect content length with unicode characters <small class="label">[language server]</small>
- fixed rare compilation pipeline crash with multiple solc versions <small class="label">[core]</small>
- fixed `wake detect` & `wake print` commands with latest `rich-click` <small class="label">[cli]</small>

## 4.9.0 <small>(Apr 25, 2024)</small> { id="4.9.0" }

Features & improvements:

- new `deploy` method for contract deployment from creation code <small class="label">[testing framework]</small>
- introduced alias `chain = default_chain` <small class="label">[testing framework]</small>
- `chain.txs` can now be indexed with numbers <small class="label">[testing framework]</small>
- `chain.chain_id` is now cast to `uint256` <small class="label">[testing framework]</small>

Fixes:

- fixed process count setting for collecting coverage <small class="label">[testing framework]</small>
- fixed pytypes generator overloading + inheritance issue <small class="label">[testing framework]</small>
- fixed LSP race conditions on files updated outside of IDE (VS Code) <small class="label">[language server]</small>
- fixed `add_hover_from_offsets` LSP printers API function <small class="label">[language server]</small>
- fixed `is_reachable` is control flow graph <small class="label">[static analysis]</small>
- fixed recursion in `expression_is_only_owner` function <small class="label">[static analysis]</small>
- fixed regex parsing from source code containing comments <small class="label">[core]</small>

## 4.8.0 <small>(Apr 5, 2024)</small> { id="4.8.0" }

Features & improvements:

- implemented callback commands for LSP printers
    - go to locations, peek locations, open URI, copy to clipboard
- Wake `console.log` is now tread as library (in respect to detectors)
- Wake `console.log` is now auto-completed in Solidity imports through LSP
- random seeds used in testing are now printed in pytest summary
- documented possible test reproducibility issues and their solutions

Fixes:

- fixed empty array encoding in new abi coder
- Python warning messages are suppressed in shell completions
- fixed LSP config loading race conditions
- newly excluded Solidity files in LSP are now treated as deleted (fixes LSP crashes)
- primitive types (e.g. `bytes32`) are now returned from `keccak256` and `read_storage_variable`
- fixed `get_variable_declarations_from_expression` recursion bug

## 4.7.0 <small>(Mar 16, 2024)</small> { id="4.7.0" }

Features:

- added support for Solidity 0.8.25

Fixes:

- fixed compilation crashes when using Solidity `log0` - `log4`
- fixed compilation crashes when using `bytes.pop()`
- fixed `random` affected by `logging` - created custom `Random` instance
- fixed compilation crashes in AST validation with Solidity <= 0.7.2

## 4.6.0 <small>(Mar 13, 2024)</small> { id="4.6.0" }

Features:

- added `visit_` functions for base classes to visitors
- added `on_revert` handler example to the default test template
- IR types (`wake.ir.types`) are now strictly comparable
- improved printing of structs and errors in call traces
- updated `axelar-proxy-contract-id` detector
- `mint_erc20`, `burn_erc20` now works with constant total supply tokens (warning is printed that total supply cannot be updated)

Fixes:

- fixed multiple issues in call traces printing
- fixed Python linter firing when using pytypes with new version of primitives types (`uint256`, etc.)
- fixed the type of `.min` `.max` members of primitive integer types
- fixed `is_reachable` helper function in `ControlFlowGraph`

## 4.5.1 <small>(Feb 17, 2024)</small> { id="4.5.1" }

Fixes:

- `ValueError` is no longer raised for experimental `abi.encode_with_signature` and `abi.encode_call` with ambiguous integers
- fixed `mint_erc20`/`burn_erc20` for most tokens

## 4.5.0 <small>(Feb 12, 2024)</small> { id="4.5.0" }

Features:

- Accounts / contracts can now be created without `default_chain` connected
- added new `unsafe-erc20-call` detector
- added support for named arguments in call traces
- `reprlib` is used again in call traces, full call traces can be enabled with `-v` CLI option
- added alias `-h` for `--help` on command-line
- added `.min` and `.max` members to int/uint types
- added new experimental `abi` coder

Fixes:

- fixed coverage collection with new Anvil
- fixed coverage collection on macOS/Windows
- fixed ambiguous errors resolving when reverting in contract constructor
- fixed ERC- slots detection using storage layout
- fixed debugger attachment when chain is not connected

## 4.4.1 <small>(Jan 30, 2024)</small> { id="4.4.1" }

Fixes:

- changed detectors/printers preview interface causing `__init__` and click entry points being run even when not intended to be run on CLI / in LSP
    - fixes `OSError(30, 'Read-only file system')` error messages in LSP on macOS
- fixed compiling projects from sources on Etherscan-like explorers in testing framework helper functions

## 4.4.0 <small>(Jan 27, 2024)</small> { id="4.4.0" }

Features:

- Solidity 0.8.24 support
- LSP providers in detectors and printers (preview)
- `ErrorDefinition` and `EventDefinition` are now supported in `pair_function_call_arguments` helper function

Fixes:

- fixed `pair_function_call_arguments` - struct construction with (possibly nested) mapping in Solidity < 0.7
- fixed LSP crash on file opened but not saved on disk

## 4.3.2 <small>(Jan 23, 2024)</small> { id="4.3.2" }

Fixes:

- fixed issue when generating pytypes for cyclically imported Solidity files with inheritance
- fixed `wake test` multiprocessing mode on macOS and Windows

## 4.3.1 <small>(Jan 9, 2024)</small> { id="4.3.1" }

Fixes:

- fixed `wake test` multiprocessing mode when running more than one test
- fixed global TOML config file not always loaded with local `wake.toml` in LSP
- fixed counter example README

## 4.3.0 <small>(Dec 24, 2023)</small> { id="4.3.0" }

Features:

- print warnings when a detector set in config options is not discovered (both on the CLI and in LSP)
- added new `complex-struct-getter` and `struct-mapping-deletion` detectors
- added new `c3-linearization` printer
- re-run detectors after modifying a loaded detector

Fixes:

- fixed Yul `return` ignored in the control flow graph
- fixed `AssertionError` in call traces when running out of gas
- fixed `abi-encode-with-signature` detector when processing signatures with nested brackets
- fixed detectors were not re-run after changing a detector-specific setting
- bumped `abch-tree-sitter` minimal version, fixing the language server crashes caused by `distutils` not being available in Python 3.12

## 4.2.0 <small>(Dec 11, 2023)</small> { id="4.2.0" }

Features:

- `wake open` command to open any Github or Etherscan-like project
- `wake up` alias for `wake init`
- new `unused-function` and `unused-modifier` detectors
- helper functions for working with storage variables now can handle whole arrays and structs
- `wake detect` and `wake print` commands now accept `--theme` options

Changes:

- changed `unused-import` detections impact from warning to info

Fixes:

- fixed compiler crashes when using SMTChecker

## 4.1.2 <small>(Dec 3 , 2023)</small> { id="4.1.2" }

Fixes:

- `solc` binaries are automatically re-installed if corrupted
- added `--silent` mode to fix LSP server crashes on Windows because of unicode

## 4.1.1 <small>(Nov 28, 2023)</small> { id="4.1.1" }

- fixed script responsible for migration to XDG paths when the global config file already exists
- fixed assertion error in ownable pattern detection, manifested mainly by `reentrancy` detector crashes

## 4.1.0 <small>(Nov 28, 2023)</small> { id="4.1.0" }

- added new printers:
    - `control-flow-graph`
    - `imports-graph`
    - `inheritance-graph`
    - `inheritance-tree`
    - `modifiers`
    - `state-changes`
- `lsp_range` and IR declaration `name_location` are now used in SARIF export
- implemented `SolidityName` Click parameter type for Solidity name shell completions
- improved `wake detect` and `wake print` help messages
- added a new `Command-line interface` docs page under the static analysis section
- state changes are now evaluated even for Yul blocks
- fixed crashes caused by `YulLiteral.value` being unset

## 4.0.1 <small>(Nov 22, 2023)</small> { id="4.0.1" }

- fixed SARIF export crashing in Github action
- fixed `wake detect` incorrect exit codes
- fixed exporting ignored detections in SARIF format
- minor changes to the documentation

## 4.0.0 <small>(Nov 20, 2023)</small> { id="4.0.0" }

- reviewed, updated and documented IR model
    - all IR nodes are now documented, generated docs available in [API reference](./api-reference/ir/abc.md) section
    - added link to SourceUnit from all IR nodes
    - added link to nearest StatementAbc from all expressions
    - added link to declaration (FunctionDefinition/ModifierDefinition) from all statements
    - added link to InlineAssembly from all Yul nodes

- updated control flow graph
    - Yul is now fully supported; InlineAssembly blocks are now decomposed into Yul statemenets
    - successful execution and reverting execution is now distinguished in control flow graph
    - assert/require/revert function calls are now handled (including these calls in conditionals)
    - fixed missing edge for in try/catch statement

- development & testing framework
    - all default accounts (`default_tx_account`, `default_call_account`, `default_estimate_account`, `default_access_list_account`) are now set by default
    - `may_revert` and `must_revert` context managers now re-raise original exception when it does not match one of arguments
    - significantly improved performance when accessing `tx.events`
    - improved event resolving algorithm
    - added `origin` field to all events, describing contract Account that emitted event
    - improved forked chain ID detection
    - `fuzz` command was integrated into `test` command
    - both single-process and multi-process tests now use pytest
        - running tests without pytest is still supported with `--no-pytest` flag

- added support for Solidity 0.8.21, 0.8.22 and 0.8.23
- added experimental support for Python 3.12
- rebranded from Woke to Wake
    - implemented automatic migration script for migrating project-specific and global files
- all CLI commands now accept `--config` option for setting local config path
- implemented `svm install --all` to install all matching solc versions
- renamed `ignore_paths` config options to `exclude_paths`
    - automatic migration script performs automatic renaming
- all solc optimizer settings may now be configured
- implemented new `wake init config` command for initializing only config file

- new detectors & printers API
    - printers are similar to detectors but allow printing (or exporting in other ways) any useful information
    - users may create custom detectors & printers using documented API
    - may be project-specific, global and loaded from plugin packages
    - project-specific detectors/printers must be first confirmed as verified to protect users downloading others (potentially malicious) projects
    - both detectors and printers may accept any number of Click options and arguments that can be set in CLI, ENV variables and TOML files
    - detector results and compiler warnings may be ignored using `// wake-disable-*` comments
    - loading priorities may be specified for multiple detectors/printers with the same name loaded from multiple plugin packages
    - `wake.analysis`, `wake.ir` and `networkx` are now imported as lazy modules to improve auto-completions speed in CLI
    - detectors cannot crash LSP server or prevent other detectors from executing, errors are reported to LSP clients
    - `logging` module logger attached to each detector/printer; logging messages are redirected to LSP client when running LSP server
    - detectors are live-reloaded after modifications when running LSP server, no need to restart LSP server to trigger changes
    - added helper CLI and LSP commands for creating new detector/printer from template
    - added more export formats to detectors and printers
    - both detectors and printers may be launched in `--watch` mode
    - implemented export to SARIF format for detectors
    - detectors may now assign dynamic impact & confidence per-detection

- implemented ready-to-use printers
    - `abi` for exporting contract ABI
    - `storage-layout` for printing contract storage layout
    - `tokens` for finding all ERC-20/ERC-721/ERC-1155 tokens in project
- improved existing detectors
- implemented new detectors
    - `abi-encode-with-signature` for detecting invalid ABI signatures
    - `incorrect-interface` for detecting incorrectly implemented ERC-20/ERC-721/ERC-1155 interface
    - `unused-import` for finding unused imports
