# Getting started

Implementing a custom detector or printer is a very efficient way to extend Wake's detection and analysis capabilities.

Both detectors and printers may be implemented as project-specific or global.

!!! tip
    Built-in [detectors](https://github.com/Ackee-Blockchain/wake/tree/main/wake_detectors) and [printers](https://github.com/Ackee-Blockchain/wake/tree/main/wake_printers) may serve as a good starting point for implementing custom detectors and printers.

## Using a template

The best way to get started is to use

```bash
wake init detector detector-name
```

or

```bash
wake init printer printer-name
```

commands, which will create a template detector or printer in `./detectors` or `./printers` respectively.
By supplying the `--global` flag, the template will be created in `$XDG_DATA_HOME/wake/global-detectors` or `$XDG_DATA_HOME/wake/global-printers` instead.

!!! tip
    If working in VS Code with the [Tools for Solidity](https://marketplace.visualstudio.com/items?itemName=AckeeBlockchain.tools-for-solidity) extension installed, the same can be achieved by running the following commands in the command palette:

    - `Tools for Solidity: New Detector`,
    - `Tools for Solidity: New Global Detector`,
    - `Tools for Solidity: New Printer`,
    - `Tools for Solidity: New Global Printer`.

## Detector & printer structure

Both template detectors and printers are implemented as a minimal Python class:

<table>
<tr>
<th>Detector</th>
<th>Printer</th>
</tr>
<tr>
<td>
```python
class MyDetectorDetector(Detector):
    _detections: List[DetectorResult]

    def __init__(self) -> None:
        self._detections = []

    def detect(self) -> List[DetectorResult]:
        return self._detections

    @detector.command(name="my-detector")
    def cli(self) -> None:
        pass
```
</td>
<td>
```python
class MyPrinterPrinter(Printer):
    def print(self) -> None:
        pass

    @printer.command(name="my-printer")
    def cli(self) -> None:
        pass
```
</td>
</tr>
</table>

Detectors define the `detect` method, which returns a list of detections. Printers define the `print` method, which prints the results of the analysis.

!!! tip
    Printers may print information from any method (even from `__init__` and `cli`), not just from `print`.

    On the contrary, printers do not need to print anything at all. For example, a printer may be used to generate a file with the results of the analysis.

### Command-line interface

[Detector][wake.detectors.api.Detector] and [Printer][wake.printers.api.Printer] subclasses should implement a command-line interface (CLI) method using the [Click](https://click.palletsprojects.com/en/8.1.x/) library.
The name of the Click command determines the name of the detector or printer. Both detectors and printers may accept additional arguments and options, for example:

```python
@printer.command(name="my-printer")
@click.argument(
    "modifier",
    type=str,
    required=True,
    help="Name of the modifier to analyze.",
)
@click.option(
    "--follow-function-calls/--no-follow-function-calls",
    is_flag=True,
    default=False,
    help="Follow function calls in the modifier.",
)
```

See the [Detector configuration](using-detectors.md#detector-configuration) and [Printer configuration](using-printers.md#printer-configuration) sections for how to set the values of arguments and options when running detectors and printers.

!!! important "Default values for detectors"
    Detectors must always provide default values for all arguments and options.

    This is because detectors may be run with `wake detect all`, where passing detector-specific arguments and options is not possible.
    The same is true for the LSP server, which runs detectors in the background.

### Inherited attributes and methods

Both [Detector][wake.detectors.api.Detector] and [Printer][wake.printers.api.Printer] classes inherit from the [Visitor][wake.core.visitor.Visitor] class, which provides `visit_` methods for all types of Solidity abstract syntax tree (AST) nodes.

Wake builds on the AST and provides an intermediate representation (IR) model, which is an extension of the AST with additional information and fixes for incorrect or missing information.
Refer to the `wake.ir` [API reference](../api-reference/ir/abc.md) for more information.

The `visit_` methods accept a single argument, which is the IR node to be visited, for example:

```python
def visit_function_definition(self, node: ir.FunctionDefinition) -> None:
    pass
```

Visit functions are automatically called by the execution engine when running the detector or printer.

Additionally, there are two methods for generating links from an IR node or from a source code location:

```python
def generate_link(self, node: ir.IrAbc) -> str:
    ...

def generate_link_from_line_col(self, path: Union[str, Path], line: int, col: int) -> str:
    ...
```

!!! Example
    The methods may be used in the following way:

    ```python
    def visit_function_definition(self, node: ir.FunctionDefinition) -> None:
        link = f"[link={self.generate_link(node)}]{node.canonical_name}[/link]"
    ```

    Refer to the [Rich](https://rich.readthedocs.io/en/stable/markup.html?highlight=link#links) documentation for more information about the syntax of console links.

### Visit modes

All detectors and printers accept unlimited number of paths to Solidity source code files and directories.
The paths are passed as command-line arguments, for example:

```bash
wake detect my-detector contracts/utils
```

When there are any paths specified, the `visit_` functions are called only for IR nodes in Solidity files in the specified paths.
However, some detectors and printers may need to visit all IR nodes in the project, to perform the analysis correctly.
In such cases, the detector or printer should override the `visit_mode` property and return `"all"` instead of the default `"paths"`.

```python
class MyDetectorDetector(Detector):
    ...

    @property
    def visit_mode(self) -> str:
        return "all"
```

When the `visit_mode` is set to `"all"`, the detector or printer is responsible for filtering out the detections or printed information that are not relevant to the specified paths.
For example:

```python
class MyPrinterPrinter(Printer):
    ...

    @property
    def visit_mode(self):
        return "all"

    def visit_contract_definition(self, node: ir.ContractDefinition) -> None:
        from wake.utils import is_relative_to
        
        if not any(is_relative_to(node.source_unit.file, p) for p in self.paths):
            return
        ...
```

### Execution order

The methods of detectors and printers are executed in the following order:

1. `__init__`,
2. Click command-line entry point (`cli` or any other method decorated with `@detector.command()` or `@printer.command()`),
3. `visit_mode`,
4. `visit_` methods in an unspecified order,
5. `detect` for detectors or `print` for printers.
