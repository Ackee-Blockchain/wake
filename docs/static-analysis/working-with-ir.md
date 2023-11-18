Wake IR (intermediate representation) model builds on top of the AST (abstract syntax tree) produced by the Solidity compiler.
It is a tree representation of the source code holding additional information.

The IR tree nodes can be divided into a few categories:

- **Declarations** - nodes that represent declarations of variables, functions, structs, etc.,
- **Statements** - nodes that control the execution flow (if, for, while, etc.) and nodes that represent a single operation ending with a semicolon (assignment, function call, etc.),
- **Expressions** - nodes that typically have a value (literals, identifiers, function calls, etc.),
- **Type names** - nodes that represent a name of a type (uint, address, etc.), usually used in a [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration],
- **Meta** - nodes typically used as helpers that do not belong to any of the above categories.

All expressions, type names and a [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration] have a type information attached to them.
See `wake.ir.types` [API reference](../../api-reference/ir/types) for more information.

## Nodes structure

The IR tree can have a very complex structure. However, there are a few rules that make it easier to understand:

- [SourceUnit][wake.ir.meta.source_unit.SourceUnit] is the root node of the IR tree,
- [FunctionDefinitions][wake.ir.declarations.function_definition.FunctionDefinition] and [ModifierDefinitions][wake.ir.declarations.modifier_definition.ModifierDefinition] hold statements,
- statements may hold other statements and expressions,
- there are only a few cases when expressions may be used without a parental statement (i.e. outside of a function/modifier body):
    - in an [InheritanceSpecifier][wake.ir.meta.inheritance_specifier.InheritanceSpecifier] argument list,
        - e.g. `:::solidity contract A is B(1, 2) {}`,
    - in a [ModifierInvocation][wake.ir.meta.modifier_invocation.ModifierInvocation] argument list,
        - e.g. `:::solidity function foo() public onlyOwner(1, 2) {}`,
    - in a [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration] initial value,
        - e.g. `:::solidity uint a = 1;`,
    - in an [ArrayTypeName][wake.ir.type_names.array_type_name.ArrayTypeName] fixed length value,
        - e.g. `:::solidity uint[2] a;`,
- only a few nodes may reference other nodes (declarations specifically):
    - [Identifier][wake.ir.expressions.identifier.Identifier] as a simple name reference,
        - e.g. `owner` referencing a variable declaration,
    - [MemberAccess][wake.ir.expressions.member_access.MemberAccess] as a member access reference,
        - e.g. `owner.balance` referencing a global symbol [ADDRESS_BALANCE][wake.ir.enums.GlobalSymbol.ADDRESS_BALANCE],
    - [IdentifierPathPart][wake.ir.meta.identifier_path.IdentifierPathPart] a helper structure used in [IdentifierPath][wake.ir.meta.identifier_path.IdentifierPath] to describe a part of a path separated by dots,
        - e.g. `Utils.IERC20` in `:::solidity contract A is Utils.IERC20 {}`,
    - [UserDefinedTypeName][wake.ir.type_names.user_defined_type_name.UserDefinedTypeName] as a reference to a user defined type,
        - e.g. `MyContract` in `:::solidity new MyContract()`,
    - [ExternalReference][wake.ir.statements.inline_assembly.ExternalReference] a helper structure describing a [YulIdentifier][wake.ir.yul.identifier.YulIdentifier] referencing a Solidity [VariableDeclaration][wake.ir.declarations.variable_declaration.VariableDeclaration],
        - e.g. `:::solidity assembly { mstore(0, owner) }`.

The following example shows the whole IR tree for a simple Solidity code snippet:

```solidity
pragma solidity ^0.8;

library Math{
    function fib(uint n) public pure returns (uint) {
        if (n < 2)
            return n;
        return fib(n - 1) + fib(n - 2);
    }
}
```

Nodes of the same category are colored the same. Both nodes and labels of edges are clickable and lead to the corresponding API documentation.
Dash edges represent a reference to another node.

<div class="excalidraw">
--8<-- "docs/images/static-analysis/ir-tree.excalidraw.svg"
</div>

!!! tip
    Since all IR nodes are iterable, it is very easy to create a simple printer to explore what parts of the source code correspond to which nodes.

    ```python
    from __future__ import annotations

    import networkx as nx
    import rich_click as click
    import wake.ir as ir
    import wake.ir.types as types
    from rich import print
    from wake.printers import Printer, printer


    class StructurePrinter(Printer):
        def print(self) -> None:
            pass

        def visit_source_unit(self, node: ir.SourceUnit):
            for n in node:
                print(f"{n}\n{n.source}\n====================")

        @printer.command(name="structure")
        def cli(self) -> None:
            pass
    ```
