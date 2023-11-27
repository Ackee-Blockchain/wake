# State changes printer

Prints all blockchain state changes performed by a function/modifier and all subsequent function calls.

## Example

<div>
--8<-- "docs/static-analysis/printers/state-changes.svg"
</div>

## Parameters

| Command-line name   | TOML name            | Type        | Default value | Description                                             |
|---------------------|----------------------|-------------|---------------|---------------------------------------------------------|
| `--name` (multiple) | <nobr>`names`</nobr> | `List[str]` | `[]`          | Function and modifier names to print state changes for. |
| `--links`           | <nobr>`links`</nobr> | `bool`      | `True`        | Whether to print links to the source code.              |
