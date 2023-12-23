from __future__ import annotations

import networkx as nx
import rich_click as click
from rich import print
from rich.tree import Tree

import wake.ir as ir
import wake.ir.types as types
from wake.printers import Printer, printer


# C3 linearization printer
class C3LinearizationPrinter(Printer):
    _interfaces: bool
    _verbose: bool

    def print(self) -> None:
        pass

    def visit_contract_definition(self, node: ir.ContractDefinition) -> None:
        tree = Tree(".")

        # Using Rich Tree strcutrue to print the C3 linearization
        def add_contract_to_tree(parent_node, n, index):
            contract_name = n.canonical_name

            contract_node = parent_node.add(
                f"{index:2d}.[bold][link={self.generate_link(n)}]{contract_name}[/link][/bold]"
            )
            # If verobose (-v/--verbose), add inheritance and constructor info
            if self._verbose:
                # Inheritance - base contracts
                if n.base_contracts:
                    base_contracts_str = ", ".join(
                        f"[blue]{x.base_name.name}[/blue]" for x in n.base_contracts
                    )
                    contract_node.add(
                        f"[italic]Base Contracts:[/italic] {base_contracts_str}"
                    )

                # Constructor and unherited constructors
                for x in n.functions:
                    if x.kind == "constructor":
                        constructor_str = (
                            f"[green]{x.canonical_name.split('.')[1]}[/green]"
                        )
                        if x.modifiers:
                            modifiers_str = ", ".join(
                                f"[green]{op.source}[/green]"
                                for op in x.modifiers
                                if op.kind == "baseConstructorSpecifier"
                            )
                            constructor_str += f", {modifiers_str}"
                        contract_node.add(
                            f"[italic]Constructor:[/italic] {constructor_str}"
                        )

            return contract_node

        # Counter for more readable output
        counter = 1
        for n in node.linearized_base_contracts:
            if not self._interfaces and n.kind == ir.enums.ContractKind.INTERFACE:
                continue

            add_contract_to_tree(tree, n, counter)
            counter += 1

        if counter > 1:
            print(
                f"[italic][link={self.generate_link(node)}]{node.name}[/link] C3 linearization ordered[/italic]"
            )
            print(tree)
            print()

    @printer.command(name="c3-linearization")
    @click.option(
        "--interfaces",
        "-i",
        is_flag=True,
        default=False,
        help="Include interfaces",
    )
    @click.option(
        "--verbose",
        "-v",
        is_flag=True,
        default=False,
        help="Show inheritance and constructors",
    )
    def cli(self, interfaces: bool, verbose: bool) -> None:
        """
        Print the C3 linearization of contracts.
        """
        self._interfaces = interfaces
        self._verbose = verbose
