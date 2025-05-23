from __future__ import annotations

import weakref
from typing import Iterator, Optional, Set, Tuple, Union

from typing_extensions import Literal

from wake.ir.abc import IrAbc, SolidityAbc
from wake.ir.ast import SolcAssignment
from wake.ir.enums import AssignmentOperator, GlobalSymbol
from wake.ir.utils import IrInitTuple
from wake.utils.decorators import weak_self_lru_cache

from ..declarations.abc import DeclarationAbc
from ..declarations.function_definition import FunctionDefinition
from ..declarations.struct_definition import StructDefinition
from ..declarations.variable_declaration import VariableDeclaration
from ..meta.source_unit import SourceUnit
from .abc import ExpressionAbc
from .conditional import Conditional
from .function_call import FunctionCall
from .identifier import Identifier
from .index_access import IndexAccess
from .member_access import MemberAccess
from .tuple_expression import TupleExpression

AssignedVariablePath = Tuple[
    Union[DeclarationAbc, SourceUnit, Literal["IndexAccess"]], ...
]


class Assignment(ExpressionAbc):
    """
    !!! example
        ```solidity
        x = 1;
        y = x = 1;
        ```
    """

    _ast_node: SolcAssignment
    _parent: weakref.ReferenceType[SolidityAbc]  # TODO: make this more specific

    _left_expression: ExpressionAbc
    _right_expression: ExpressionAbc
    _operator: AssignmentOperator

    def __init__(
        self, init: IrInitTuple, assignment: SolcAssignment, parent: SolidityAbc
    ):
        super().__init__(init, assignment, parent)
        self._operator = assignment.operator
        self._left_expression = ExpressionAbc.from_ast(
            init, assignment.left_hand_side, self
        )
        self._right_expression = ExpressionAbc.from_ast(
            init, assignment.right_hand_side, self
        )

    def __iter__(self) -> Iterator[IrAbc]:
        yield self
        yield from self._left_expression
        yield from self._right_expression

    @property
    def parent(self) -> SolidityAbc:
        return super().parent

    @property
    def children(self) -> Iterator[ExpressionAbc]:
        """
        Yields:
            Direct children of this node.
        """
        yield self._left_expression
        yield self._right_expression

    @property
    def left_expression(self) -> ExpressionAbc:
        """
        Must be L-value (something that can be assigned to).

        Returns:
            Left expression of the assignment.
        """
        return self._left_expression

    @property
    def right_expression(self) -> ExpressionAbc:
        """
        Returns:
            Right expression of the assignment.
        """
        return self._right_expression

    @property
    def operator(self) -> AssignmentOperator:
        """
        Returns:
            Operator used in the assignment.
        """
        return self._operator

    @property
    @weak_self_lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        return self.left_expression.is_ref_to_state_variable

    @property
    def assigned_variables(self) -> Tuple[Optional[Set[AssignedVariablePath]], ...]:
        """
        WARNING:
            Is not considered stable and so is not exported in the documentation.
        """

        def resolve_node(node: ExpressionAbc) -> Set[AssignedVariablePath]:
            if isinstance(node, Conditional):
                return resolve_node(node.true_expression) | resolve_node(
                    node.false_expression
                )
            elif isinstance(node, Identifier):
                referenced_declaration = node.referenced_declaration
                assert isinstance(referenced_declaration, (DeclarationAbc, SourceUnit))
                return {(referenced_declaration,)}
            elif isinstance(node, IndexAccess):
                return {
                    path + ("IndexAccess",)
                    for path in resolve_node(node.base_expression)
                }
            elif isinstance(node, MemberAccess):
                referenced_declaration = node.referenced_declaration
                assert isinstance(referenced_declaration, (DeclarationAbc, SourceUnit))
                return {
                    path + (referenced_declaration,)
                    for path in resolve_node(node.expression)
                }
            elif isinstance(node, FunctionCall):
                function_called = node.function_called
                if function_called is None:
                    return set()
                elif isinstance(function_called, (GlobalSymbol, VariableDeclaration)):
                    # global function or variable getter called
                    # variable getter may return different type than variable declaration (structs with arrays and mappings)
                    # return empty set for now
                    return set()
                elif isinstance(function_called, FunctionDefinition):
                    # cannot be handled in the current implementation, return empty set for now
                    return set()
                elif isinstance(function_called, StructDefinition):
                    return {(function_called,)}
                else:
                    assert False, f"Unexpected node type: {type(node)}\n{self.source}"
            elif isinstance(node, TupleExpression) and len(node.components) == 1:
                return resolve_node(node.components[0])
            else:
                assert False, f"Unexpected node type: {type(node)}\n{self.source}"

        node = self.left_expression
        if isinstance(node, TupleExpression):
            return tuple(
                resolve_node(expression) if expression is not None else None
                for expression in node.components
            )
        else:
            return (resolve_node(node),)
