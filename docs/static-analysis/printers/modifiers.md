# Modifiers printer

Prints modifiers with their usages.

## Example

<div>
--8<-- "docs/static-analysis/printers/modifiers.svg"
</div>

## Parameters

| Command-line name                                                         | TOML name                      | Type        | Default value | Description                                                     |
|---------------------------------------------------------------------------|--------------------------------|-------------|---------------|-----------------------------------------------------------------|
| `--name` (multiple)                                                       | <nobr>`names`</nobr>           | `List[str]` | `[]`          | Modifier names.                                                 |
| <nobr>`--canonical-names`</nobr>/<br/><nobr>`--no-canonical-names`</nobr> | <nobr>`canonical_names`</nobr> | `bool`      | `True`        | Whether to print (full) canonical names instead of local names. |
| <nobr>`--code-snippets`</nobr>/<br/><nobr>`--no-code-snippets`</nobr>     | <nobr>`code_snippets`</nobr>   | `bool`      | `True`        | Whether to print modifier source code snippets.                 |
