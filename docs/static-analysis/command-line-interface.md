# Command-line interface

Detectors and printers provide a command-line interface through the [Click](https://click.palletsprojects.com/en/8.1.x/) library.
It is recommended to read the Click documentation for information about how to use it.
This section provides additional tips how to make command-line interactions with detectors and printers more user-friendly.

## Name completions

Wake offers a custom `SolidityName` click type that can be used with Click options and arguments to provide name completions for Solidity functions, modifiers, etc.

!!! info
    Refer to the [Installation](../installation.md) section for how to enable shell completions.

!!! warning
    `SolidityName` completions are only available after the project has been compiled.

The `SolidityName` type accepts one or multiple types of auto-completed names represented by the following constants:

- `"contract"`,
- `"enum"`,
- `"error"`,
- `"event"`,
- `"function"`,
- `"modifier"`,
- `"struct"`,
- `"user_defined_value_type`,
- `"variable"`.

Additionally, the `SolidityName` type accepts the following boolean keyword arguments:

- `case_sensitive` - whether the completions should be case-sensitive,
- `canonical` - whether canonical names should be auto-completed, e.g. `ContractName.functionName`,
- `non_canonical` - whether non-canonical (local) names should be auto-completed, e.g. `functionName`.

!!! example
    In the following example, both canonical and non-canonical function and modifier names are auto-completed case-insensitively:
    ```python
    @click.option(
        "--name",
        "-n",
        "names",
        type=SolidityName("function", "modifier", case_sensitive=False),
        multiple=True,
        help="Function and modifier names",
    )
    ```

## Imports

In order to have the shell completions as quick as possible, all unnecessary imports should be avoided or delayed for the time when the command is actually run.
To achieve this, it is the best to follow these recommendations:

- It is strongly recommended to start with the templates provided by the `wake up` command.
- Any additionally needed imports should be placed inside functions and methods, not at the top of the file.
- `networkx`, `wake.ir` and `wake.ir.types` modules are lazy-loaded, their members should not be accessed at the top level of the file or at the top level of the detector/printer class.
    - This is not necessary for type annotations as long as `:::python from __future__ import annotations` is used.

The following example shows common patterns that lead to additional delays in shell completions:

```python linenums="1" hl_lines="6 18-24"
from __future__ import annotations

from pathlib import Path  # (1)!
from typing import Set, Tuple, Union

import graphviz  # (2)!
import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer


class MyPrinter(Printer):
    restricted_nodes = (  # (3)!
        ir.Identifier,
        ir.IndexAccess,
        ir.IndexRangeAccess,
        ir.Literal,
        ir.MemberAccess,
    )

    ...
```

1. Both `pathlib` and `typing` modules may be imported at the top level of the file as they are imported by the Wake runtime anyway.
2. `graphviz` module is not lazy-loaded, it should be imported inside a function or a method that uses it.
3. `wake.ir` members accessed at the top level of the class. This will case the module to be loaded. Instead, a property or a helper function should be used:
