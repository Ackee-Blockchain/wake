# Inheritance tree printer

Prints inheritance trees of contracts in given paths or in the whole project.

## Example

<div>
--8<-- "docs/static-analysis/printers/inheritance-tree.svg"
</div>

## Parameters

| Command-line name   | TOML name            | Type        | Default value | Description                                       |
|---------------------|----------------------|-------------|---------------|---------------------------------------------------|
| `--name` (multiple) | <nobr>`names`</nobr> | `List[str]` | `[]`          | Contract names to generate inheritance trees for. |
