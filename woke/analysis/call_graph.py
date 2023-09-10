import logging
from typing import Iterable, Union

import networkx as nx

import woke.ir.types as types
from woke.ir import (
    BinaryOperation,
    ExternalReference,
    FunctionCall,
    FunctionCallOptions,
    FunctionDefinition,
    IdentifierPathPart,
    MemberAccess,
    ModifierDefinition,
    ModifierInvocation,
    SourceUnit,
    UnaryOperation,
)
from woke.ir.enums import GlobalSymbol

logger = logging.getLogger(__name__)


class CallGraph:
    _graph: nx.DiGraph

    def __init__(self, source_units: Iterable[SourceUnit]):
        self._graph = nx.DiGraph()

        for source_unit in source_units:
            for func in source_unit.functions:
                # free functions
                self._graph.add_node(func)
            for contract in source_unit.contracts:
                for func in contract.functions:
                    self._graph.add_node(func)
                for mod in contract.modifiers:
                    self._graph.add_node(mod)

        node: Union[FunctionDefinition, ModifierDefinition]
        for node in self._graph.nodes:
            if isinstance(node, ModifierDefinition):
                for ref in node.references:
                    if isinstance(
                        ref, (ExternalReference, BinaryOperation, UnaryOperation)
                    ):
                        # should not happen
                        continue
                    elif isinstance(ref, IdentifierPathPart):
                        ref = ref.underlying_node

                    parent = ref.parent
                    if isinstance(parent, ModifierInvocation):
                        self._graph.add_edge(
                            parent.parent, node, call=parent, external=False
                        )
                    else:
                        logger.warning(
                            f"Unexpected parent of modifier reference: {parent.source}"
                        )

            for ref in node.references:
                if isinstance(ref, (ExternalReference, IdentifierPathPart)):
                    # should not be possible to call a function from assembly or using identifier path
                    continue
                elif isinstance(ref, (BinaryOperation, UnaryOperation)):
                    if ref.statement is not None:
                        # should always be true
                        self._graph.add_edge(
                            ref.statement.declaration, node, call=ref, external=False
                        )
                    continue

                parent = ref.parent
                while (
                    isinstance(parent, MemberAccess)
                    and parent.referenced_declaration
                    in {
                        GlobalSymbol.FUNCTION_VALUE,
                        GlobalSymbol.FUNCTION_GAS,
                    }
                    or isinstance(parent, FunctionCallOptions)
                ):
                    if isinstance(parent, MemberAccess):
                        parent = parent.parent.parent
                    else:
                        parent = parent.parent

                if isinstance(parent, MemberAccess):
                    if parent.member_name == "selector":
                        pass  # TODO
                elif (
                    isinstance(parent, FunctionCall) and parent.function_called == node
                ):
                    if parent.statement is None:
                        # should not happen
                        continue

                    t = parent.expression.type
                    if not isinstance(t, types.Function):
                        logger.warning(
                            f"Unexpected function call type: {parent.type} ({parent.source})"
                        )
                        continue

                    self._graph.add_edge(
                        parent.statement.declaration,
                        node,
                        call=parent,
                        external=(
                            t.kind
                            in {
                                types.FunctionTypeKind.EXTERNAL,
                                types.FunctionTypeKind.DELEGATE_CALL,
                                types.FunctionTypeKind.BARE_CALL,
                                types.FunctionTypeKind.BARE_CALL_CODE,
                                types.FunctionTypeKind.BARE_DELEGATE_CALL,
                                types.FunctionTypeKind.BARE_STATIC_CALL,
                            }
                        ),
                    )

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph.copy(as_view=True)  # pyright: ignore reportGeneralTypeIssues
