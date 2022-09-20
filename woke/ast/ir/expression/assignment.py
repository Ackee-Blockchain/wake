from functools import lru_cache
from typing import Iterator, Optional, Set, Tuple, Union

from typing_extensions import Literal

from woke.ast.enums import AssignmentOperator, ModifiesStateFlag
from woke.ast.ir.abc import IrAbc, SolidityAbc
from woke.ast.ir.utils import IrInitTuple
from woke.ast.nodes import SolcAssignment

from ..declaration.abc import DeclarationAbc
from .abc import ExpressionAbc
from .conditional import Conditional
from .identifier import Identifier
from .index_access import IndexAccess
from .member_access import MemberAccess
from .tuple_expression import TupleExpression

AssignedVariablePath = Tuple[Union[DeclarationAbc, Literal["IndexAccess"]], ...]


class Assignment(ExpressionAbc):
    """
    TBD
    """

    _ast_node: SolcAssignment
    _parent: SolidityAbc  # TODO: make this more specific

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
        return self._parent

    @property
    def left_expression(self) -> ExpressionAbc:
        return self._left_expression

    @property
    def right_expression(self) -> ExpressionAbc:
        return self._right_expression

    @property
    def operator(self) -> AssignmentOperator:
        return self._operator

    @property
    @lru_cache(maxsize=2048)
    def is_ref_to_state_variable(self) -> bool:
        return self.left_expression.is_ref_to_state_variable

    @property
    @lru_cache(maxsize=2048)
    def modifies_state(self) -> Set[Tuple[IrAbc, ModifiesStateFlag]]:
        ret = self.left_expression.modifies_state | self.right_expression.modifies_state
        if self.left_expression.is_ref_to_state_variable:
            ret |= {(self, ModifiesStateFlag.MODIFIES_STATE_VAR)}
        return ret

    @property
    @lru_cache(maxsize=2048)
    def assigned_variables(self) -> Tuple[Optional[Set[AssignedVariablePath]], ...]:
        def resolve_node(node: ExpressionAbc) -> Set[AssignedVariablePath]:
            if isinstance(node, Conditional):
                return resolve_node(node.true_expression) | resolve_node(
                    node.false_expression
                )
            elif isinstance(node, Identifier):
                referenced_declaration = node.referenced_declaration
                assert isinstance(referenced_declaration, DeclarationAbc)
                return {(referenced_declaration,)}
            elif isinstance(node, IndexAccess):
                return {
                    path + ("IndexAccess",)
                    for path in resolve_node(node.base_expression)
                }
            elif isinstance(node, MemberAccess):
                referenced_declaration = node.referenced_declaration
                assert isinstance(referenced_declaration, DeclarationAbc)
                return {
                    path + (referenced_declaration,)
                    for path in resolve_node(node.expression)
                }
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
