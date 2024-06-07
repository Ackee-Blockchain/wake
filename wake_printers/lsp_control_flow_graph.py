from __future__ import annotations

from typing import TYPE_CHECKING, Tuple, Union

import networkx as nx
import rich_click as click
from rich import print

import wake.ir as ir
import wake.ir.types as types
from wake.cli import SolidityName
from wake.printers import Printer, printer

if TYPE_CHECKING:
    from typing_extensions import Literal


class LspControlFlowGraphPrinter(Printer):
    execution_mode = "lsp"

    _direction: Literal["LR", "RL", "TB", "BT"]
    _urls: bool

    def print(self) -> None:
        pass

    def _generate_cfg(
        self,
        declaration: Union[
            ir.FunctionDefinition, ir.ModifierDefinition, ir.YulFunctionDefinition
        ],
    ) -> str:
        import graphviz as gv

        from wake.analysis.cfg import CfgNode

        cfg = declaration.cfg
        graph = cfg.graph

        g = gv.Digraph(
            f"{declaration.canonical_name} control flow graph"
            if not isinstance(declaration, ir.YulFunctionDefinition)
            else f"{declaration.name} control flow graph"
        )
        g.attr(rankdir=self._direction)
        g.attr("node", shape="box")

        skip_start_node = False
        if (
            len(cfg.start_node.statements) == 0
            and cfg.start_node.control_statement is None
            and graph.out_degree(
                cfg.start_node
            )  # pyright: ignore reportGeneralTypeIssues
            == 1
        ):
            skip_start_node = True

        node: CfgNode
        for node in graph.nodes:  # pyright: ignore reportGeneralTypeIssues
            if skip_start_node and node == cfg.start_node:
                continue

            statements: Tuple[
                Union[ir.StatementAbc, ir.YulStatementAbc], ...
            ] = node.statements
            node_attrs = {
                "label": "".join(
                    f"{line}\l"  # pyright: ignore reportInvalidStringEscapeSequence
                    for line in str(node).splitlines()
                )
            }

            if node == cfg.success_end_node:
                node_attrs["color"] = "green"
                node_attrs["xlabel"] = "success"
            elif node == cfg.revert_end_node:
                node_attrs["color"] = "red"
                node_attrs["xlabel"] = "revert"

            if self._urls and len(statements) > 0:
                first_statement = statements[0]
                line, column = declaration.source_unit.get_line_col_from_byte_offset(
                    first_statement.byte_location[0]
                )
                node_attrs[
                    "URL"
                ] = f"vscode://file/{first_statement.source_unit.file}:{line}:{column}"
            g.node(str(node.id), **node_attrs)

        for (
            from_,
            to,
            data,
        ) in graph.edges.data():  # pyright: ignore reportGeneralTypeIssues
            if skip_start_node and from_ == cfg.start_node:
                continue

            condition = data["condition"]  # pyright: ignore reportOptionalSubscript
            if condition[1] is not None:
                label = f"{condition[1].source} {condition[0]}"
            else:
                label = condition[0]
            g.edge(str(from_.id), str(to.id), label=label)

        return g.source

    def _on_click(
        self,
        node: Union[
            ir.FunctionDefinition, ir.ModifierDefinition, ir.YulFunctionDefinition
        ],
    ) -> None:
        from wake.core.lsp_provider import ShowDotCommand

        assert self.lsp_provider is not None
        self.lsp_provider.add_commands(
            [
                ShowDotCommand(
                    title=(
                        f"{node.canonical_name} control flow graph"
                        if not isinstance(node, ir.YulFunctionDefinition)
                        else f"{node.name} control flow graph"
                    ),
                    dot=self._generate_cfg(node),
                )
            ]
        )

    def visit_function_definition(self, node: ir.FunctionDefinition):
        if not node.implemented:
            return

        assert self.lsp_provider is not None
        self.lsp_provider.add_code_lens(
            node,
            "Control flow graph",
            on_click=lambda: self._on_click(node),
        )

    def visit_modifier_definition(self, node: ir.ModifierDefinition):
        if not node.implemented:
            return

        assert self.lsp_provider is not None
        self.lsp_provider.add_code_lens(
            node,
            "Control flow graph",
            on_click=lambda: self._on_click(node),
        )

    def visit_yul_function_definition(self, node: ir.YulFunctionDefinition):
        assert self.lsp_provider is not None
        self.lsp_provider.add_code_lens(
            node,
            "Control flow graph",
            on_click=lambda: self._on_click(node),
        )

    @printer.command(name="lsp-control-flow-graph")
    @click.option(
        "--direction", type=click.Choice(["LR", "RL", "TB", "BT"]), default="TB"
    )
    @click.option("--urls", is_flag=True, default=True)
    def cli(self, direction: Literal["LR", "RL", "TB", "BT"], urls: bool) -> None:
        self._direction = direction
        self._urls = urls
